import pytest

from src.lib.video.scanner import calculate_hash, is_video_file, scan_directory


class TestScanner:
    @pytest.fixture
    def test_dir(self, tmp_path):
        """Create a temporary directory with files."""
        # Create structure
        # /
        #   video1.mp4
        #   video2.MOV
        #   image.jpg
        #   subdir/
        #     video3.mkv

        (tmp_path / "video1.mp4").write_text("content1")
        (tmp_path / "video2.MOV").write_text("content2")
        (tmp_path / "image.jpg").write_text("image")

        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "video3.mkv").write_text("content3")

        return tmp_path

    def test_is_video_file(self, tmp_path):
        """Test extension filtering."""
        # Create dummy files
        f1 = tmp_path / "test.mp4"
        f1.touch()
        f2 = tmp_path / "TEST.MOV"
        f2.touch()
        f3 = tmp_path / "test.txt"
        f3.touch()
        f4 = tmp_path / ".hidden"
        f4.touch()

        assert is_video_file(f1) is True
        assert is_video_file(f2) is True
        assert is_video_file(f3) is False
        assert is_video_file(f4) is False

    def test_scan_directory(self, test_dir):
        """Test recursive scanning."""
        files = list(scan_directory(str(test_dir)))
        filenames = [f.name for f in files]

        assert len(files) == 3
        assert "video1.mp4" in filenames
        assert "video2.MOV" in filenames
        assert "video3.mkv" in filenames
        assert "image.jpg" not in filenames

    def test_scan_nonexistent_directory(self, tmp_path):
        """Test scanning a missing directory."""
        files = list(scan_directory(str(tmp_path / "missing")))
        assert len(files) == 0

    def test_calculate_hash(self, tmp_path):
        """Test fast hashing (just checking consistency, not algo correctness per se)."""
        f = tmp_path / "test.mp4"
        f.write_text("test content" * 1000)

        hash1 = calculate_hash(f)
        hash2 = calculate_hash(f)

        assert hash1 == hash2
        assert len(hash1) > 0
