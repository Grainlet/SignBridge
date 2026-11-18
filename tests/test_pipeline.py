from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

import config
from app import create_app
from backend.audio_extraction import AudioExtractionError, extract_audio_to_wav
from backend.sign_matcher import match_translated_segments, resolve_gloss_clip
from backend.sign_translation import translate_sentence, translate_sentences
from backend.transcription import group_words_into_sentences, is_vosk_model_ready, transcribe_wav
from backend.video_input import VideoInputError, is_allowed_video_filename, validate_youtube_url


class TestVideoInputValidation(unittest.TestCase):
    def test_allowed_extensions(self) -> None:
        self.assertTrue(is_allowed_video_filename("sample.mp4"))
        self.assertTrue(is_allowed_video_filename("DEMO.MOV"))
        self.assertFalse(is_allowed_video_filename("notes.txt"))
        self.assertFalse(is_allowed_video_filename("archive.zip"))

    def test_youtube_url_validation(self) -> None:
        self.assertEqual(
            validate_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        self.assertEqual(
            validate_youtube_url("https://youtu.be/dQw4w9WgXcQ"),
            "https://youtu.be/dQw4w9WgXcQ",
        )
        with self.assertRaises(VideoInputError):
            validate_youtube_url("")
        with self.assertRaises(VideoInputError):
            validate_youtube_url("https://example.com/video.mp4")
        with self.assertRaises(VideoInputError):
            validate_youtube_url("https://www.youtube.com/watch?v=short")


class TestSentenceGrouping(unittest.TestCase):
    def test_groups_on_pause_gap(self) -> None:
        words = [
            {"start": 0.0, "end": 0.4, "text": "hello", "confidence": 0.99},
            {"start": 0.45, "end": 0.8, "text": "everyone", "confidence": 0.99},
            {"start": 2.0, "end": 2.4, "text": "welcome", "confidence": 0.98},
        ]
        sentences = group_words_into_sentences(words, pause_threshold=0.75)
        self.assertEqual(len(sentences), 2)
        self.assertEqual(sentences[0]["text"], "Hello everyone")
        self.assertEqual(sentences[0]["start"], 0.0)
        self.assertEqual(sentences[0]["end"], 0.8)
        self.assertEqual(sentences[1]["text"], "Welcome")


class TestAslTranslationAndMatching(unittest.TestCase):
    def test_phrase_and_grammar_translation(self) -> None:
        vocab = {"how", "you", "your", "name", "what", "good", "morning", "school", "go", "today"}
        res1 = translate_sentence({"id": "seg_1", "start": 0.0, "end": 1.5, "text": "Hello, how are you?"}, vocab=vocab | {"hello"})
        self.assertEqual(res1["glosses"], ["hello", "how", "you"])
        self.assertEqual(res1["asl_status"], "matched")

        res2 = translate_sentence({"id": "seg_2", "start": 1.6, "end": 3.0, "text": "What is your name?"}, vocab=vocab)
        self.assertEqual(res2["glosses"], ["your", "name", "what"])
        self.assertEqual(res2["asl_status"], "matched")

        res3 = translate_sentence({"id": "seg_3", "start": 3.1, "end": 5.0, "text": "We go to school today"}, vocab=vocab | {"we"})
        self.assertEqual(res3["glosses"][0], "today")
        self.assertNotIn("to", res3["glosses"])

    def test_missing_words_are_never_fabricated(self) -> None:
        vocab = {"hello", "bird"}
        res = translate_sentence(
            {"id": "seg_1", "start": 0.0, "end": 2.0, "text": "Hello xylophone quantum"},
            vocab=vocab,
        )
        self.assertEqual(res["asl_status"], "partial")
        self.assertEqual(res["glosses"], ["hello"])
        self.assertEqual(res["missing_words"], ["xylophone", "quantum"])

        unavail = translate_sentence(
            {"id": "seg_2", "start": 2.0, "end": 4.0, "text": "Xylophone quantum"},
            vocab=vocab,
        )
        self.assertEqual(unavail["asl_status"], "unavailable")
        self.assertFalse(unavail["asl_available"])

    def test_starter_sign_clip_resolution(self) -> None:
        clip = resolve_gloss_clip("hello")
        self.assertIsNotNone(clip)
        self.assertTrue(Path(clip["video_path"]).exists())

        matched = match_translated_segments(
            translate_sentences(
                [{"id": "seg_0001", "start": 0.0, "end": 2.0, "text": "Good morning, thank you"}]
            )
        )
        self.assertEqual(matched[0]["asl_status"], "matched")
        self.assertGreaterEqual(len(matched[0]["clips"]), 3)


class TestAudioExtractionAndFlaskAPI(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app()
        self.client = self.app.test_client()
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="signbridge_test_"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_health_and_library_endpoints(self) -> None:
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["ffmpeg"])
        self.assertTrue(data["ffprobe"])
        self.assertTrue(data["vosk_model"])
        self.assertGreaterEqual(data["wlasl_gloss_count"], 2000)
        self.assertGreaterEqual(data["starter_signs_count"], 50)

        lib_resp = self.client.get("/api/library")
        self.assertEqual(lib_resp.status_code, 200)
        self.assertGreaterEqual(lib_resp.get_json()["starter_signs_count"], 50)

    def test_ffmpeg_extract_and_vosk_silence_pipeline(self) -> None:
        if not is_vosk_model_ready():
            self.skipTest("Vosk model not present")

        sample_mp4 = self.tmp_dir / "silence_test.mp4"
        subprocess.run(
            [
                config.FFMPEG_BINARY,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=320x180:d=1.5",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=44100:cl=stereo",
                "-t",
                "1.5",
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                str(sample_mp4),
            ],
            check=True,
            capture_output=True,
        )

        wav_out = self.tmp_dir / "out.wav"
        info = extract_audio_to_wav(sample_mp4, wav_out)
        self.assertTrue(info.has_audio)
        self.assertTrue(wav_out.exists())

        transcript_json = self.tmp_dir / "transcript.json"
        transcript = transcribe_wav(wav_out, transcript_json)
        self.assertTrue(transcript_json.exists())
        self.assertTrue(transcript["no_speech_detected"])
        self.assertEqual(transcript["text"], "")

    def test_video_without_audio_fails_gracefully(self) -> None:
        no_audio_mp4 = self.tmp_dir / "no_audio.mp4"
        subprocess.run(
            [
                config.FFMPEG_BINARY,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=320x180:d=1",
                "-c:v",
                "libx264",
                str(no_audio_mp4),
            ],
            check=True,
            capture_output=True,
        )
        with self.assertRaises(AudioExtractionError):
            extract_audio_to_wav(no_audio_mp4, self.tmp_dir / "never.wav")

    def test_upload_endpoint_end_to_end_compiles_interpreter(self) -> None:
        sample_mp4 = self.tmp_dir / "upload_test.mp4"
        subprocess.run(
            [
                config.FFMPEG_BINARY,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=320x180:d=1.2",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=44100:cl=stereo",
                "-t",
                "1.2",
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                str(sample_mp4),
            ],
            check=True,
            capture_output=True,
        )

        with open(sample_mp4, "rb") as fh:
            resp = self.client.post(
                "/api/upload",
                data={"video": (fh, "upload_test.mp4")},
                content_type="multipart/form-data",
            )
        self.assertEqual(resp.status_code, 202)
        job_id = resp.get_json()["job_id"]

        final_status = None
        for _ in range(60):
            job_resp = self.client.get(f"/api/jobs/{job_id}")
            self.assertEqual(job_resp.status_code, 200)
            payload = job_resp.get_json()
            if payload["status"] in {"completed", "failed"}:
                final_status = payload
                break
            time.sleep(0.25)

        try:
            self.assertIsNotNone(final_status)
            self.assertEqual(final_status["status"], "completed")

            p_resp = self.client.get(f"/api/player/{job_id}")
            self.assertEqual(p_resp.status_code, 200)
            p_data = p_resp.get_json()
            self.assertTrue(p_data["interpreter_available"])
            self.assertIn("/api/video/", p_data["original_video_url"])
            self.assertIn("/api/video/", p_data["interpreter_video_url"])

            s_resp = self.client.get(f"/api/sync/{job_id}")
            self.assertEqual(s_resp.status_code, 200)
            self.assertTrue(s_resp.get_json()["asl_compiled"])

            v_resp = self.client.get(f"/api/video/{job_id}/interpreter")
            self.assertEqual(v_resp.status_code, 200)
        finally:
            self.client.delete(f"/api/jobs/{job_id}")


if __name__ == "__main__":
    unittest.main()
