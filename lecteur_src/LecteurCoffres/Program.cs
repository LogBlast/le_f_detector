// LecteurCoffres : lit un replay Fortnite (.replay) et compte les coffres du joueur qui l'a enregistré.
// Sortie : une ligne JSON par replay (ouverts, à esprit, rares, cassés).
//
// Décodage des replays : bibliothèque FortniteReplayDecompressor (Shiqan, licence MIT), avec les correctifs
// de LED-N/Fortnite-ChestCounter (licence MIT) — voir lib/. La logique de comptage ci-dessous est propre à ce projet.
//
// Usage : LecteurCoffres <fichier.replay> [<fichier2.replay> ...]

using System.Text.Json;
using FortniteReplayReader.Models;
using FortniteReplayReader.Models.NetFieldExports;
using FortniteReplayReader.Models.NetFieldExports.Items;
using Unreal.Core;
using Unreal.Core.Contracts;
using Unreal.Core.Models;
using Unreal.Core.Models.Enums;

foreach (var fichier in args)
{
    object resultat;
    try
    {
        using var flux = File.Open(fichier, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
        resultat = new Lecteur().Analyser(flux, Path.GetFileName(fichier));
    }
    catch (Exception e)
    {
        resultat = new { fichier = Path.GetFileName(fichier), erreur = e.GetType().Name + ": " + e.Message };
    }
    Console.WriteLine(JsonSerializer.Serialize(resultat));
}
return 0;

static class Types
{
    public const string Normal = "normal", Rare = "rare", Esprit = "esprit", Autre = "autre", PasCoffre = "";

    /// <summary>Type de coffre d'après le nom du blueprint ("" = pas un coffre : munitions, nourriture, canon...).</summary>
    public static string Classer(string bp)
    {
        var b = bp.ToLowerInvariant();
        if (b.StartsWith("prop_")) return PasCoffre;
        if (b.Contains("cannon") || b.Contains("ammo") || b.Contains("foodbox") || b.Contains("food_box")) return PasCoffre;
        if (b.Contains("rarechest") || b.Contains("rare_chest") || b.Contains("legendary")) return Rare;
        if (b.Contains("relic") || b.Contains("extraction") || b.Contains("spriteposter") || b.Contains("booty")) return Esprit;
        if (b.Contains("tiered_chest") || b.Contains("normalchest") || b.Contains("standardchest") || b.Contains("buried")) return Normal;
        return b.Contains("chest") ? Autre : PasCoffre;
    }
}

sealed class Lecteur : FortniteReplayReader.ReplayReader
{
    private sealed record Fouille(float Temps, string Cle, string Nom, uint Pion, bool Casse);

    static Lecteur()
    {
        // Les coffres dont le blueprint n'est pas connu de la bibliothèque sont lus comme des conteneurs génériques.
        NetFieldParser.AliasResolver = chemin =>
        {
            if (chemin.Contains(':') || chemin.EndsWith("_ClassNetCache", StringComparison.Ordinal)) return null;
            var nom = chemin[(chemin.LastIndexOf('/') + 1)..];
            if (nom.StartsWith("BGA_DelilahTreasureHuntAnimatedChest", StringComparison.Ordinal)) return null; // coffre doré de récompense
            return chemin.Contains("/Containers/", StringComparison.OrdinalIgnoreCase) || nom.Contains("Chest", StringComparison.OrdinalIgnoreCase)
                ? GenericContainer.GroupPath : null;
        };
    }

    private static float Maintenant => Unreal.Core.ReplayReader<FortniteReplay>.CurrentTime;

    private readonly Dictionary<uint, string> _cle = new(), _nom = new();
    private readonly Dictionary<uint, float> _ouvertA = new();
    private readonly Dictionary<uint, uint> _dernierFouilleur = new();
    private readonly Dictionary<uint, bool> _fouille = new();
    private readonly Dictionary<string, uint> _dernierOuvreur = new();
    private readonly HashSet<string> _vus = new();
    private readonly List<Fouille> _fouilles = new();
    private readonly Dictionary<uint, uint> _pionVersEtat = new();
    private readonly Dictionary<uint, int> _etatVersId = new();

    public Lecteur() : base(null, ParseMode.Normal) { }

    private string Chemin(uint? guid) => guid is uint g && g != 0 && _netGuidCache.TryGetPathName(g, out var p) ? p : "";

    private static string NomCourt(string chemin)
    {
        var nom = chemin[(chemin.LastIndexOf('/') + 1)..];
        var point = nom.LastIndexOf('.');
        if (point >= 0) nom = nom[(point + 1)..];
        var uaid = nom.IndexOf("_UAID_", StringComparison.Ordinal);
        return uaid >= 0 ? nom[..uaid] : nom;
    }

    protected override void OnChannelOpened(uint canal, NetworkGUID? acteur)
    {
        base.OnChannelOpened(canal, acteur);
        var c = Channels[canal];
        var archetype = Chemin(c?.ArchetypeId);
        var cheminActeur = Chemin(c?.ActorId);
        var nom = NomCourt(archetype != "" ? archetype : cheminActeur);

        // Clé stable : chemin dans la carte, sinon position (coffres apparus en cours de partie)
        _cle[canal] = cheminActeur != "" ? cheminActeur
            : c?.Actor?.Location is { } l && Types.Classer(nom) != Types.PasCoffre ? $"{nom}@{l.X:F0},{l.Y:F0}"
            : $"guid:{c?.ActorId}";
        _nom[canal] = nom;
        _ouvertA[canal] = Maintenant;
        _fouille.Remove(canal);
        _dernierFouilleur.Remove(canal);
    }

    protected override void OnExportRead(uint canal, INetFieldExportGroup? groupe)
    {
        base.OnExportRead(canal, groupe);
        switch (groupe)
        {
            case BaseContainer coffre:
                if (coffre.SearchingPawn is uint f && f != 0) _dernierFouilleur[canal] = f;
                var cle = _cle.GetValueOrDefault(canal, $"ch:{canal}");
                var nom = _nom.GetValueOrDefault(canal, "?");
                // État reçu à l'ouverture du canal = coffre déjà ouvert avant d'être visible
                var ancien = Maintenant - _ouvertA.GetValueOrDefault(canal, float.MinValue) < 0.5f;
                var stable = !cle.StartsWith("guid:") && !cle.StartsWith("ch:");

                if (coffre.bAlreadySearched == false)
                {
                    _fouille[canal] = false; // coffre (re)rempli : il pourra être recompté
                }
                else if (coffre.bAlreadySearched == true && !_fouille.GetValueOrDefault(canal))
                {
                    _fouille[canal] = true;
                    if (_dernierFouilleur.TryGetValue(canal, out var ouvreur))
                    {
                        var dejaCompte = ancien && (stable
                            ? _dernierOuvreur.TryGetValue(cle, out var avant) && avant == ouvreur
                            : _vus.Contains(cle));
                        if (!dejaCompte && (!ancien || stable))
                        {
                            _vus.Add(cle);
                            _dernierOuvreur[cle] = ouvreur;
                            _fouilles.Add(new Fouille(Maintenant, cle, nom, ouvreur, false));
                        }
                    }
                }
                else if (coffre.bDestroyed && coffre.SearchingPawn is uint casseur && casseur != 0
                         && (_vus.Add(cle) || (_fouille.TryGetValue(canal, out var etait) && !etait)))
                {
                    // Cassé au lieu d'être ouvert : le serveur met le casseur dans SearchingPawn
                    _fouille[canal] = true;
                    _dernierOuvreur[cle] = casseur;
                    _fouilles.Add(new Fouille(Maintenant, cle, nom, casseur, true));
                }
                break;

            case PlayerPawn pion when pion.PlayerState is uint ps && ps != 0:
                if (Channels[canal]?.ActorId is uint idPion) _pionVersEtat[idPion] = ps;
                break;

            case FortPlayerState etat:
                var id = etat.PlayerId is null ? etat.PlayerID : (int?)etat.PlayerId;
                if (Channels[canal]?.ActorId is uint idEtat && id != null) _etatVersId[idEtat] = id.Value;
                break;
        }
    }

    public object Analyser(Stream flux, string fichier)
    {
        var replay = ReadReplay(flux);

        // Le joueur qui a enregistré le replay (toi), et tous ses pions (un nouveau à chaque réapparition)
        var etats = new HashSet<uint>();
        if (replay.GameData?.RecorderId is uint enregistreur)
        {
            etats.Add(enregistreur);
            if (_etatVersId.TryGetValue(enregistreur, out var monId))
                foreach (var kv in _etatVersId.Where(kv => kv.Value == monId)) etats.Add(kv.Key);
        }
        var mesPions = _pionVersEtat.Where(kv => etats.Contains(kv.Value)).Select(kv => kv.Key).ToHashSet();
        string? pseudo = null;
        if (replay.GameData?.RecorderId is uint r && _etatVersId.TryGetValue(r, out var pid))
            pseudo = replay.PlayerData?.FirstOrDefault(p => p.Id == pid)?.PlayerName;

        var coffres = _fouilles
            .Where(x => mesPions.Contains(x.Pion))
            .Select(x => (x.Temps, Type: Types.Classer(x.Nom), x.Nom, x.Casse))
            .Where(x => x.Type != Types.PasCoffre)
            .OrderBy(x => x.Temps)
            .ToList();

        return new
        {
            fichier,
            joueur = pseudo,
            debut = replay.Info?.Timestamp,
            en_cours = replay.Info?.IsLive == true || IsPartialReplay,  // partie pas finie : à relire plus tard
            ouverts = coffres.Count(c => !c.Casse),
            esprit = coffres.Count(c => !c.Casse && c.Type == Types.Esprit),
            rare = coffres.Count(c => !c.Casse && c.Type == Types.Rare),
            casse = coffres.Count(c => c.Casse),
            details = coffres.Select(c => new { t = MathF.Round(c.Temps, 1), type = c.Type, nom = c.Nom, casse = c.Casse }),
        };
    }
}
