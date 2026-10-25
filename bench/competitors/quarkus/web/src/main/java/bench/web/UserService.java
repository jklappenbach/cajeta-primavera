package bench.web;

import jakarta.inject.Singleton;

@Singleton
public class UserService {
    private final IdMinter minter;

    public UserService(IdMinter minter) {
        this.minter = minter;
    }

    public Account register(Signup s, String registeredBy) {
        return new Account(minter.mint(s.username()), s.username(), false, registeredBy);
    }
}
