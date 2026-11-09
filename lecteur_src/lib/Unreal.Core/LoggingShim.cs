// Remplace Microsoft.Extensions.Logging.Abstractions (journalisation désactivée) :
// le lecteur n'a besoin d'aucune dépendance en dehors du runtime .NET.
namespace Microsoft.Extensions.Logging;

public interface ILogger { }

public static class LoggerExtensions
{
    public static void LogDebug(this ILogger? logger, string? message, params object?[] args) { }
    public static void LogInformation(this ILogger? logger, string? message, params object?[] args) { }
    public static void LogWarning(this ILogger? logger, string? message, params object?[] args) { }
    public static void LogError(this ILogger? logger, string? message, params object?[] args) { }
    public static void LogError(this ILogger? logger, System.Exception? exception, string? message, params object?[] args) { }
}
