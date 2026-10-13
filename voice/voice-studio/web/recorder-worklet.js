class VoiceStudioRecorder extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.buffer = new Float32Array(2048);
    this.position = 0;
    this.frames = 0;
    this.maximumFrames = options.processorOptions.maximumFrames;
    this.finished = false;
    this.port.onmessage = event => {
      if (event.data === 'finish') this.finish();
    };
  }
  flush() {
    if (!this.position) return;
    const chunk = this.buffer.slice(0, this.position);
    this.port.postMessage({type:'samples', samples:chunk}, [chunk.buffer]);
    this.position = 0;
  }
  finish() {
    if (this.finished) return;
    this.finished = true;
    this.flush();
    this.port.postMessage({type:'finished'});
  }
  process(inputs, outputs) {
    for (const output of outputs) for (const channel of output) channel.fill(0);
    if (this.finished) return true;
    const channels = inputs[0];
    if (!channels?.length) return true;
    for (let index = 0; index < channels[0].length; index++) {
      let sample = 0;
      for (const channel of channels) sample += channel[index] || 0;
      this.buffer[this.position++] = sample / channels.length;
      this.frames++;
      if (this.position === this.buffer.length) this.flush();
      if (this.frames >= this.maximumFrames) { this.finish(); break; }
    }
    return true;
  }
}
registerProcessor('voice-studio-recorder', VoiceStudioRecorder);
