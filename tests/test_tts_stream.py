"""Streaming TTS: sentence pipelining and the blocking/half-duplex contract."""
import threading
import time

from voice.text_to_speech import BufferedSpeechStream, EdgeSpeechStream, EdgeTTS


def fake_engine(plays, mixer_ready=True):
    """An EdgeTTS whose synthesis is recorded instead of played."""
    engine = EdgeTTS.__new__(EdgeTTS)
    engine.voice = "test"
    engine._mixer_ready = mixer_ready
    engine._lock = threading.Lock()
    engine.play_one = lambda text: (plays.append(text), True)[1]
    return engine


def wait_for(plays, expected):
    """Playback happens on a worker thread, so give it a moment to land."""
    deadline = time.time() + 5
    while time.time() < deadline and plays != expected:
        time.sleep(0.02)
    assert plays == expected


def test_sentences_play_as_they_arrive():
    plays: list[str] = []
    stream = EdgeSpeechStream(fake_engine(plays))
    stream.feed("The weather is sunny today. It is")
    wait_for(plays, ["The weather is sunny today."])
    stream.feed(" also warm outside.")
    stream.finish()
    assert plays == ["The weather is sunny today.", "It is also warm outside."]
    assert stream.spoke is True


def test_short_openings_fold_into_the_next_sentence():
    plays: list[str] = []
    stream = EdgeSpeechStream(fake_engine(plays))
    stream.feed("Done. I opened Chrome and searched for the latest AI news.")
    stream.finish()
    assert plays == ["Done. I opened Chrome and searched for the latest AI news."]


def test_ragged_word_deltas_reassemble_sentences():
    plays: list[str] = []
    stream = EdgeSpeechStream(fake_engine(plays))
    for word in ["Why ", "don't ", "skeletons ", "fight ", "each ", "other? ",
                 "They ", "don't ", "have ", "the ", "guts."]:
        stream.feed(word)
    stream.finish()
    assert plays == ["Why don't skeletons fight each other?", "They don't have the guts."]


def test_unpunctuated_reply_flushes_near_the_boundary():
    plays: list[str] = []
    stream = EdgeSpeechStream(fake_engine(plays))
    text = " ".join(f"segment{i}" for i in range(120))
    for word in text.split():
        stream.feed(word + " ")
    stream.finish()
    assert len(plays) >= 2
    assert max(len(chunk) for chunk in plays) < 500
    assert " ".join(plays).split() == text.split()


def test_finish_blocks_until_playback_drains():
    started = threading.Event()
    gate = threading.Event()
    playing: list[str] = []

    engine = EdgeTTS.__new__(EdgeTTS)
    engine.voice = "test"
    engine._mixer_ready = True
    engine._lock = threading.Lock()

    def blocking_play(text):
        playing.append(text)
        started.set()
        gate.wait(5)
        return True

    engine.play_one = blocking_play
    stream = EdgeSpeechStream(engine)
    stream.feed("First sentence lands here. Second sentence lands here.")
    started.wait(5)
    assert playing == ["First sentence lands here."]

    gate.set()
    stream.finish()
    assert playing == ["First sentence lands here.", "Second sentence lands here."]
    assert stream.spoke is True


def test_no_mixer_means_nothing_was_spoken():
    stream = EdgeSpeechStream(fake_engine([], mixer_ready=False))
    stream.feed("Hello there, how are you today?")
    stream.finish()
    assert stream.spoke is False, "caller must fall back to speak()"


def test_buffered_stream_speaks_once_at_the_end():
    spoken: list[str] = []

    class Dummy:
        def speak(self, text):
            spoken.append(text)

    stream = BufferedSpeechStream(Dummy())
    stream.feed("Part one. ")
    stream.feed("part two.")
    assert spoken == []
    stream.finish()
    assert spoken == ["Part one. part two."]
    assert stream.spoke is True
