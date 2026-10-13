// Forwards captured audio (already resampled to the context rate, 16 kHz) to the
// offscreen page in ~100 ms blocks.
class DualSubsTap extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buf = new Float32Array(1600);
    this.len = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (input && input.length) {
      const channels = input.length;
      const frames = input[0].length;
      for (let i = 0; i < frames; i++) {
        let sum = 0;
        for (let c = 0; c < channels; c++) sum += input[c][i];
        this.buf[this.len++] = sum / channels;
        if (this.len === this.buf.length) {
          this.port.postMessage(this.buf.slice(0));
          this.len = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor('dualsubs-tap', DualSubsTap);
