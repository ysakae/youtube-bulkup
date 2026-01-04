from src.lib.auth.profiles import (
    DEFAULT_PROFILE,
    get_active_profile,
    get_profile_path,
    list_profiles,
    set_active_profile,
)


class TestProfiles:
    # Removed incomplete test_default_profile

    def test_set_get_active_profile(self, tmp_path, mocker):
        # Patch constants to use tmp_path
        mocker.patch("src.lib.auth.profiles.TOKENS_DIR", tmp_path / "tokens")
        mocker.patch("src.lib.auth.profiles.ACTIVE_PROFILE_FILE", tmp_path / ".active_profile")
        
        assert get_active_profile() == DEFAULT_PROFILE
        
        set_active_profile("test_user")
        assert get_active_profile() == "test_user"
        
        assert (tmp_path / ".active_profile").read_text() == "test_user"
        assert (tmp_path / "tokens").exists()

    def test_list_profiles(self, tmp_path, mocker):
        tokens_dir = tmp_path / "tokens"
        tokens_dir.mkdir()
        mocker.patch("src.lib.auth.profiles.TOKENS_DIR", tokens_dir)
        
        (tokens_dir / "user1.pickle").touch()
        (tokens_dir / "user2.pickle").touch()
        
        profiles = list_profiles()
        assert "user1" in profiles
        assert "user2" in profiles
        assert len(profiles) == 2

    def test_get_profile_path(self, tmp_path, mocker):
        mocker.patch("src.lib.auth.profiles.TOKENS_DIR", tmp_path / "tokens")
        path = get_profile_path("test")
        assert path == tmp_path / "tokens" / "test.pickle"

    def test_delete_profile_token(self, tmp_path, mocker):
        from src.lib.auth.profiles import delete_profile_token
        
        mocker.patch("src.lib.auth.profiles.TOKENS_DIR", tmp_path / "tokens")
        token_path = tmp_path / "tokens" / "test.pickle"
        token_path.parent.mkdir()
        token_path.touch()
        
        assert delete_profile_token("test") is True
        assert not token_path.exists()
        
    def test_delete_profile_token_not_exists(self, tmp_path, mocker):
        from src.lib.auth.profiles import delete_profile_token
        
        mocker.patch("src.lib.auth.profiles.TOKENS_DIR", tmp_path / "tokens")
        
        assert delete_profile_token("nonexistent") is False
