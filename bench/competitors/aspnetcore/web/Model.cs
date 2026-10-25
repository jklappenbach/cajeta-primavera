using System.ComponentModel.DataAnnotations;
using System.Text;
using System.Text.Json.Serialization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.ModelBinding;

namespace Web;

/// The request-scoped principal the authentication middleware fills in.
public sealed class RequestPrincipal
{
    public string Name { get; set; } = "";
}

/// Mints `u-` + the 32-bit FNV-1a of the username's UTF-8 bytes.
public sealed class IdMinter
{
    public string Mint(string username)
    {
        uint h = 0x811c9dc5;
        foreach (byte b in Encoding.UTF8.GetBytes(username))
        {
            h ^= b;
            h = unchecked(h * 16777619u);
        }
        return "u-" + h.ToString("x8");
    }
}

public sealed class UserService(IdMinter minter)
{
    public Account Register(Signup s, string principal) =>
        new(minter.Mint(s.Username!), s.Username!, false, principal);
}

public sealed class Signup
{
    [Required(ErrorMessage = Validation.UsernameRequired)]
    [StringLength(64, MinimumLength = 3, ErrorMessage = Validation.UsernameLength)]
    [JsonPropertyName("username")]
    public string? Username { get; set; }

    [Required(ErrorMessage = Validation.PasswordRequired)]
    [MinLength(8, ErrorMessage = Validation.PasswordLength)]
    [JsonPropertyName("password")]
    public string? Password { get; set; }
}

public sealed record Account(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("username")] string Username,
    [property: JsonPropertyName("confirmed")] bool Confirmed,
    [property: JsonPropertyName("registeredBy")] string RegisteredBy);

public sealed record ErrorBody([property: JsonPropertyName("error")] string Error);

/// Maps DataAnnotations failures onto the contract's bodies, first rule first.
public static class Validation
{
    public const string UsernameRequired = "username is required";
    public const string PasswordRequired = "password is required";
    public const string UsernameLength = "username must be 3 to 64 characters";
    public const string PasswordLength = "password must be at least 8 characters";
    static readonly string[] Order = [UsernameRequired, PasswordRequired, UsernameLength, PasswordLength];

    public static IActionResult Respond(ActionContext ctx)
    {
        var messages = new List<string>();
        foreach (var (key, entry) in ctx.ModelState)
        {
            foreach (var e in entry.Errors)
            {
                if (Array.IndexOf(Order, e.ErrorMessage) >= 0) messages.Add(e.ErrorMessage);
                // A value of the wrong JSON type fails binding, not an attribute.
                else if (key.Contains("username", StringComparison.OrdinalIgnoreCase)) messages.Add(UsernameRequired);
                else if (key.Contains("password", StringComparison.OrdinalIgnoreCase)) messages.Add(PasswordRequired);
            }
        }
        var first = Order.FirstOrDefault(messages.Contains) ?? "invalid request";
        return new ObjectResult(new ErrorBody(first)) { StatusCode = 400 };
    }
}

public sealed record Fortune(int Id, string Message);

/// The twelve rows of bench/contract/fortunes.json.
public sealed class FortuneRepository
{
    public IReadOnlyList<Fortune> All { get; } =
    [
        new(1, "fortune: No such file or directory"),
        new(2, "A computer scientist is someone who fixes things that aren't broken."),
        new(3, "After enough decimal places, nobody gives a damn."),
        new(4, "A bad random number generator: 1, 1, 1, 1, 1, 4.33e+67, 1, 1, 1"),
        new(5, "A computer program does what you tell it to do, not what you want it to do."),
        new(6, "Emacs is a nice operating system, but I prefer UNIX. — Tom Christaensen"),
        new(7, "Any program that runs right is obsolete."),
        new(8, "A list is only as strong as its weakest link. — Donald Knuth"),
        new(9, "Feature: A bug with seniority."),
        new(10, "Computers make very fast, very accurate mistakes."),
        new(11, "<script>alert(\"This should not be displayed in a browser alert box.\");</script>"),
        new(12, "フレームワークのベンチマーク"),
    ];
}

[ApiController]
public sealed class UsersController(UserService users, RequestPrincipal principal) : ControllerBase
{
    [HttpPost("/users")]
    public IActionResult Register([FromBody] Signup s) =>
        StatusCode(201, users.Register(s, principal.Name));
}

public sealed class FortunesController(FortuneRepository repo) : Controller
{
    [HttpGet("/fortunes")]
    public IActionResult Index()
    {
        var rows = repo.All.ToList();
        rows.Sort((a, b) => string.CompareOrdinal(a.Message, b.Message));
        return View(rows);
    }
}
