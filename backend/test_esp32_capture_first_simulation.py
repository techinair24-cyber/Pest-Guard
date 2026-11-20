import re
import unittest
from pathlib import Path


FIRMWARE_PATH = Path(__file__).resolve().parents[1] / "p1_oct1a.ino"
FIRMWARE_SOURCE = FIRMWARE_PATH.read_text(encoding="utf-8-sig")


def firmware_constant(pattern):
    match = re.search(pattern, FIRMWARE_SOURCE)
    if match is None:
        raise AssertionError(f"Firmware constant not found: {pattern}")
    return int(match.group(1))


SAMPLE_RATE = firmware_constant(
    r"constexpr uint32_t SAMPLE_RATE\s*=\s*(\d+)"
)
RECORD_SECONDS = firmware_constant(
    r"constexpr uint32_t RECORD_SECONDS\s*=\s*(\d+)"
)
TOTAL_SAMPLES = SAMPLE_RATE * RECORD_SECONDS
PCM_PAYLOAD_BYTES = TOTAL_SAMPLES * 2
CHUNK_SAMPLES = firmware_constant(
    r"constexpr size_t AUDIO_CHUNK_SAMPLES\s*=\s*(\d+)"
)


def signed_pcm_sample(index):
    value = (index * 40503 + 0x5A17) & 0xFFFF
    return value - 0x10000 if value >= 0x8000 else value


def i2s_word(sample):
    value = (sample & 0xFFFF) << 16
    return value - 0x100000000 if value >= 0x80000000 else value


def make_i2s_reads(samples, read_sizes):
    words = [i2s_word(sample) for sample in samples]
    reads = []
    offset = 0
    read_index = 0
    while offset < len(words):
        count = min(read_sizes[read_index % len(read_sizes)], len(words) - offset)
        reads.append(words[offset : offset + count])
        offset += count
        read_index += 1
    return reads


class CaptureFirstSimulation:
    def __init__(self, *, psram_available=True, largest_free_block=PCM_PAYLOAD_BYTES):
        self.psram_available = psram_available
        self.largest_free_block = largest_free_block
        self.capture_buffer = None
        self.i2s_read_count = 0
        self.transmission_delay_samples = 0

    def capture(self, i2s_reads):
        if (
            not self.psram_available
            or self.largest_free_block < PCM_PAYLOAD_BYTES
        ):
            return False

        buffer = bytearray(PCM_PAYLOAD_BYTES)
        captured_samples = 0
        read_index = 0

        while captured_samples < TOTAL_SAMPLES:
            if read_index >= len(i2s_reads):
                return False

            words = i2s_reads[read_index]
            read_index += 1
            self.i2s_read_count += 1
            remaining = TOTAL_SAMPLES - captured_samples
            if not words or len(words) > min(CHUNK_SAMPLES, remaining):
                return False

            for word in words:
                sample = (word >> 16) & 0xFFFF
                if sample >= 0x8000:
                    sample -= 0x10000
                position = captured_samples * 2
                buffer[position : position + 2] = sample.to_bytes(
                    2, "little", signed=True
                )
                captured_samples += 1

        self.capture_buffer = bytes(buffer)
        return True

    def transmit(
        self,
        read_sizes,
        delayed_read_indices=(),
        delay_samples=0,
    ):
        if self.capture_buffer is None:
            return b""

        payload = bytearray()
        read_index = 0
        while len(payload) < PCM_PAYLOAD_BYTES:
            size = read_sizes[read_index % len(read_sizes)]
            payload.extend(
                self.capture_buffer[
                    len(payload) : len(payload) + size
                ]
            )
            if read_index in delayed_read_indices:
                self.transmission_delay_samples += delay_samples
            read_index += 1
        return bytes(payload)


class CaptureFirstSimulationTests(unittest.TestCase):
    def setUp(self):
        self.samples = [signed_pcm_sample(index) for index in range(TOTAL_SAMPLES)]
        self.expected_pcm = b"".join(
            sample.to_bytes(2, "little", signed=True)
            for sample in self.samples
        )

    def test_capture_preserves_order_signed_pcm_and_exact_length(self):
        simulator = CaptureFirstSimulation()
        self.assertTrue(
            simulator.capture(
                make_i2s_reads(self.samples, [CHUNK_SAMPLES])
            )
        )

        self.assertEqual(len(simulator.capture_buffer), PCM_PAYLOAD_BYTES)
        self.assertEqual(simulator.capture_buffer, self.expected_pcm)

    def test_partial_i2s_reads_are_concatenated_without_gaps(self):
        simulator = CaptureFirstSimulation()
        partial_sizes = [1, 17, 255, 128, 3, CHUNK_SAMPLES]
        self.assertTrue(
            simulator.capture(
                make_i2s_reads(self.samples, partial_sizes)
            )
        )

        self.assertEqual(simulator.capture_buffer, self.expected_pcm)

    def test_missing_psram_or_contiguous_space_fails_before_capture(self):
        for simulator in (
            CaptureFirstSimulation(psram_available=False),
            CaptureFirstSimulation(
                largest_free_block=PCM_PAYLOAD_BYTES - 1
            ),
        ):
            self.assertFalse(
                simulator.capture(make_i2s_reads(self.samples, [CHUNK_SAMPLES]))
            )
            self.assertIsNone(simulator.capture_buffer)
            self.assertEqual(simulator.i2s_read_count, 0)
            self.assertEqual(simulator.transmit([512]), b"")

    def test_incomplete_i2s_capture_is_never_transmitted(self):
        simulator = CaptureFirstSimulation()
        incomplete = make_i2s_reads(
            self.samples[: TOTAL_SAMPLES - 1],
            [CHUNK_SAMPLES],
        )
        self.assertFalse(simulator.capture(incomplete))
        self.assertIsNone(simulator.capture_buffer)
        self.assertEqual(simulator.transmit([512]), b"")

    def test_delayed_transmission_reuses_the_complete_capture(self):
        simulator = CaptureFirstSimulation()
        self.assertTrue(
            simulator.capture(
                make_i2s_reads(self.samples, [CHUNK_SAMPLES])
            )
        )
        reads_before_transmission = simulator.i2s_read_count
        payload = simulator.transmit(
            [1, 3, 511, 1024],
            delayed_read_indices=(2, 8),
            delay_samples=int(SAMPLE_RATE * 0.6),
        )

        self.assertEqual(payload, self.expected_pcm)
        self.assertEqual(len(payload), PCM_PAYLOAD_BYTES)
        self.assertEqual(simulator.i2s_read_count, reads_before_transmission)
        self.assertEqual(
            simulator.transmission_delay_samples,
            int(SAMPLE_RATE * 1.2),
        )


if __name__ == "__main__":
    unittest.main()
