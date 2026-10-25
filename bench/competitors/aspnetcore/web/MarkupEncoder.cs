using System.Text.Encodings.Web;

namespace Web;

/// HTML encoding of exactly the five markup characters (& < > " '), the set
/// Jinja2/MarkupSafe, Thymeleaf and Qute escape. The framework's default
/// HtmlEncoder also always encodes '+' and every non-ASCII character
/// (`&#x2B;`, `&#x30D5;`), which no other engine on the page does.
public sealed class MarkupEncoder : HtmlEncoder
{
    public override int MaxOutputCharactersPerInputCharacter => 6;

    public override bool WillEncode(int unicodeScalar) =>
        unicodeScalar is '&' or '<' or '>' or '"' or '\'';

    public override unsafe int FindFirstCharacterToEncode(char* text, int textLength)
    {
        for (int i = 0; i < textLength; i++)
        {
            if (WillEncode(text[i])) return i;
        }
        return -1;
    }

    public override unsafe bool TryEncodeUnicodeScalar(int unicodeScalar, char* buffer, int bufferLength,
        out int numberOfCharactersWritten)
    {
        string rep = unicodeScalar switch
        {
            '&' => "&amp;",
            '<' => "&lt;",
            '>' => "&gt;",
            '"' => "&quot;",
            '\'' => "&#39;",
            _ => char.ConvertFromUtf32(unicodeScalar),
        };
        if (rep.Length > bufferLength)
        {
            numberOfCharactersWritten = 0;
            return false;
        }
        for (int i = 0; i < rep.Length; i++) buffer[i] = rep[i];
        numberOfCharactersWritten = rep.Length;
        return true;
    }
}
