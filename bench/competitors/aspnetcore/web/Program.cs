// ASP.NET Core competitor for the primavera benchmark (bench/contract/README.md).
using System.Text.Encodings.Web;
using Microsoft.AspNetCore.Mvc;
using Web;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddSingleton<IdMinter>();
builder.Services.AddSingleton<UserService>();
builder.Services.AddSingleton<FortuneRepository>();
builder.Services.AddScoped<RequestPrincipal>();
// Razor escapes the five markup characters and nothing else (see MarkupEncoder);
// registered before MVC, whose own registration is TryAdd.
builder.Services.AddSingleton<HtmlEncoder>(new MarkupEncoder());
builder.Services.AddControllersWithViews()
    .ConfigureApiBehaviorOptions(o => o.InvalidModelStateResponseFactory = Validation.Respond);

var app = builder.Build();

// The authentication filter: guards /users, stores the principal in request scope.
app.Use(async (context, next) =>
{
    if (context.Request.Path.StartsWithSegments("/users"))
    {
        if (context.Request.Headers.Authorization.ToString() != "Bearer bench-7f3c9a1e")
        {
            context.Response.StatusCode = 401;
            context.Response.ContentType = "application/json";
            await context.Response.WriteAsync("{\"error\":\"unauthorized\"}");
            return;
        }
        context.RequestServices.GetRequiredService<RequestPrincipal>().Name = "bench-client";
    }
    await next(context);
});

app.MapGet("/health", () => Results.Json(new Health("up")));
app.MapControllers();
app.Run();

record Health(string status);
