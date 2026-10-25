package bench;

import jakarta.inject.Singleton;
import java.nio.charset.StandardCharsets;

/** `u-` and the 32-bit FNV-1a of the username's UTF-8 bytes, eight lowercase hex digits. */
@Singleton
public class IdMinter {
    public String mint(String username) {
        int h = 0x811c9dc5;
        for (byte b : username.getBytes(StandardCharsets.UTF_8)) {
            h ^= (b & 0xff);
            h *= 16777619;
        }
        String hex = Integer.toHexString(h);
        return "u-" + "00000000".substring(hex.length()) + hex;
    }
}
