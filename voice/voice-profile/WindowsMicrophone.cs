using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

namespace SccVoiceRecorder {
    public sealed class InputDevice {
        public int Id { get; set; }
        public string Name { get; set; }
    }
    public sealed class WavAnalysis {
        public double DurationSeconds { get; set; }
        public double Rms { get; set; }
        public double Peak { get; set; }
        public double ClippedFraction { get; set; }
        public int SampleRate { get; set; }
        public int Channels { get; set; }
    }
    public static class WindowsMicrophone {
        private const uint HeaderDone = 1;
        private const int SampleRate = 24000;
        [StructLayout(LayoutKind.Sequential, Pack = 2)]
        private struct WaveFormat {
            public ushort FormatTag, Channels;
            public uint SamplesPerSec, AvgBytesPerSec;
            public ushort BlockAlign, BitsPerSample, ExtraSize;
        }
        [StructLayout(LayoutKind.Sequential)]
        private struct WaveHeader {
            public IntPtr Data;
            public uint BufferLength, BytesRecorded;
            public UIntPtr User;
            public uint Flags, Loops;
            public IntPtr Next;
            public UIntPtr Reserved;
        }
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct WaveCaps {
            public ushort Manufacturer, Product;
            public uint DriverVersion;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string Name;
            public uint Formats;
            public ushort Channels, Reserved;
        }
        private sealed class Buffer {
            public IntPtr Data, Header;
            public bool Prepared;
        }
        [DllImport("winmm.dll")] private static extern uint waveInGetNumDevs();
        [DllImport("winmm.dll", CharSet = CharSet.Unicode)] private static extern uint waveInGetDevCapsW(UIntPtr device, out WaveCaps caps, uint size);
        [DllImport("winmm.dll")] private static extern uint waveInOpen(out IntPtr handle, uint device, ref WaveFormat format, IntPtr callback, IntPtr instance, uint flags);
        [DllImport("winmm.dll")] private static extern uint waveInPrepareHeader(IntPtr handle, IntPtr header, uint size);
        [DllImport("winmm.dll")] private static extern uint waveInUnprepareHeader(IntPtr handle, IntPtr header, uint size);
        [DllImport("winmm.dll")] private static extern uint waveInAddBuffer(IntPtr handle, IntPtr header, uint size);
        [DllImport("winmm.dll")] private static extern uint waveInStart(IntPtr handle);
        [DllImport("winmm.dll")] private static extern uint waveInStop(IntPtr handle);
        [DllImport("winmm.dll")] private static extern uint waveInReset(IntPtr handle);
        [DllImport("winmm.dll")] private static extern uint waveInClose(IntPtr handle);
        [DllImport("winmm.dll", CharSet = CharSet.Unicode)] private static extern uint waveInGetErrorTextW(uint error, StringBuilder text, uint size);
        private static void Check(uint status, string operation) {
            if (status == 0) return;
            StringBuilder text = new StringBuilder(256);
            waveInGetErrorTextW(status, text, 256);
            throw new IOException(operation + ": " + text.ToString() + " (" + status + ")");
        }
        private static WaveFormat Format() {
            return new WaveFormat { FormatTag = 1, Channels = 1, SamplesPerSec = SampleRate,
                AvgBytesPerSec = SampleRate * 2, BlockAlign = 2, BitsPerSample = 16, ExtraSize = 0 };
        }
        public static InputDevice[] GetDevices() {
            List<InputDevice> devices = new List<InputDevice>();
            for (uint id = 0; id < waveInGetNumDevs(); id++) {
                WaveCaps caps;
                Check(waveInGetDevCapsW(new UIntPtr(id), out caps, (uint)Marshal.SizeOf(typeof(WaveCaps))), "Mikrofonabfrage");
                devices.Add(new InputDevice { Id = (int)id, Name = caps.Name });
            }
            return devices.ToArray();
        }
        public static bool SupportsFormat(int deviceId) {
            WaveFormat format = Format(); IntPtr ignored;
            return waveInOpen(out ignored, unchecked((uint)deviceId), ref format, IntPtr.Zero, IntPtr.Zero, 1) == 0;
        }
        // The operator invokes Capture only after reading the own-voice consent.
        // CALLBACK_NULL keeps all buffer handling on this thread, including cleanup.
        public static void Capture(string path, int deviceId, int seconds) {
            if (seconds < 15 || seconds > 30) throw new ArgumentOutOfRangeException("seconds", "15-30 Sekunden erforderlich.");
            if (File.Exists(path)) throw new IOException("Aufnahmedatei existiert bereits.");
            IntPtr handle = IntPtr.Zero;
            List<Buffer> buffers = new List<Buffer>();
            int headerSize = Marshal.SizeOf(typeof(WaveHeader));
            int bufferBytes = SampleRate; // Half a second, PCM16 mono.
            int wantedBytes = seconds * SampleRate * 2;
            bool complete = false;
            MemoryStream audio = new MemoryStream(wantedBytes);
            try {
                WaveFormat format = Format();
                Check(waveInOpen(out handle, unchecked((uint)deviceId), ref format, IntPtr.Zero, IntPtr.Zero, 0), "Mikrofon oeffnen");
                for (int i = 0; i < 8; i++) {
                    Buffer buffer = new Buffer();
                    buffers.Add(buffer);
                    buffer.Data = Marshal.AllocHGlobal(bufferBytes);
                    buffer.Header = Marshal.AllocHGlobal(headerSize);
                    WaveHeader header = new WaveHeader { Data = buffer.Data, BufferLength = (uint)bufferBytes };
                    Marshal.StructureToPtr(header, buffer.Header, false);
                    Check(waveInPrepareHeader(handle, buffer.Header, (uint)headerSize), "Aufnahme vorbereiten");
                    buffer.Prepared = true;
                    Check(waveInAddBuffer(handle, buffer.Header, (uint)headerSize), "Aufnahmepuffer bereitstellen");
                }
                Check(waveInStart(handle), "Aufnahme starten");
                Stopwatch clock = Stopwatch.StartNew();
                double nextDisplay = 0;
                int nextBuffer = 0;
                while (audio.Length < wantedBytes) {
                    if (clock.Elapsed.TotalSeconds > seconds + 5) throw new IOException("Mikrofon liefert keine ausreichenden Audiodaten. Windows-Mikrofonzugriff pruefen.");
                    if (!Console.IsInputRedirected && Console.KeyAvailable && Console.ReadKey(true).Key == ConsoleKey.Escape)
                        throw new OperationCanceledException("Aufnahme abgebrochen.");
                    Buffer buffer = buffers[nextBuffer];
                    WaveHeader header = (WaveHeader)Marshal.PtrToStructure(buffer.Header, typeof(WaveHeader));
                    if ((header.Flags & HeaderDone) != 0) {
                        int count = Math.Min((int)header.BytesRecorded, wantedBytes - (int)audio.Length);
                        if (count > 0) {
                            byte[] bytes = new byte[count]; Marshal.Copy(buffer.Data, bytes, 0, count); audio.Write(bytes, 0, count);
                        }
                        if (audio.Length < wantedBytes) Check(waveInAddBuffer(handle, buffer.Header, (uint)headerSize), "Aufnahmepuffer erneuern");
                        nextBuffer = (nextBuffer + 1) % buffers.Count;
                    } else { Thread.Sleep(10); }
                    if (clock.Elapsed.TotalSeconds >= nextDisplay) {
                        Console.Write("\rAufnahme: {0:0}/{1} s - ESC bricht ab.   ", Math.Min(clock.Elapsed.TotalSeconds, seconds), seconds);
                        nextDisplay = clock.Elapsed.TotalSeconds + 0.25;
                    }
                }
                waveInStop(handle);
                using (BinaryWriter writer = new BinaryWriter(File.Open(path, FileMode.CreateNew, FileAccess.Write, FileShare.None))) {
                    writer.Write(Encoding.ASCII.GetBytes("RIFF")); writer.Write((uint)(36 + audio.Length));
                    writer.Write(Encoding.ASCII.GetBytes("WAVEfmt ")); writer.Write((uint)16);
                    writer.Write((ushort)1); writer.Write((ushort)1); writer.Write((uint)SampleRate);
                    writer.Write((uint)(SampleRate * 2)); writer.Write((ushort)2); writer.Write((ushort)16);
                    writer.Write(Encoding.ASCII.GetBytes("data")); writer.Write((uint)audio.Length);
                    audio.Position = 0; audio.CopyTo(writer.BaseStream);
                }
                complete = true;
            } finally {
                if (handle != IntPtr.Zero) waveInReset(handle);
                foreach (Buffer buffer in buffers) {
                    if (buffer.Prepared) {
                        uint result = waveInUnprepareHeader(handle, buffer.Header, (uint)headerSize);
                        if (result != 0) {
                            // Reset returns every queued header. A short retry covers driver lag.
                            Thread.Sleep(20); result = waveInUnprepareHeader(handle, buffer.Header, (uint)headerSize);
                        }
                        if (result != 0) continue; // Do not free memory still owned by a driver.
                    }
                    if (buffer.Header != IntPtr.Zero) Marshal.FreeHGlobal(buffer.Header);
                    if (buffer.Data != IntPtr.Zero) Marshal.FreeHGlobal(buffer.Data);
                }
                if (handle != IntPtr.Zero) waveInClose(handle);
                audio.Dispose();
                Console.WriteLine();
                if (!complete && File.Exists(path)) File.Delete(path);
            }
        }
        public static WavAnalysis AnalyzeWav(string path) {
            using (BinaryReader reader = new BinaryReader(File.OpenRead(path))) {
                if (reader.BaseStream.Length < 44 || new string(reader.ReadChars(4)) != "RIFF") throw new InvalidDataException("Keine gueltige WAV-Datei.");
                uint riffSize = reader.ReadUInt32();
                if ((long)riffSize + 8 != reader.BaseStream.Length || new string(reader.ReadChars(4)) != "WAVE") throw new InvalidDataException("WAV-Datei ist unvollstaendig.");
                ushort channels = 0, bits = 0, format = 0; uint rate = 0;
                long dataOffset = -1; uint dataLength = 0;
                while (reader.BaseStream.Position + 8 <= reader.BaseStream.Length) {
                    string id = new string(reader.ReadChars(4)); uint length = reader.ReadUInt32();
                    long next = reader.BaseStream.Position + length + (length % 2);
                    if (next > reader.BaseStream.Length) throw new InvalidDataException("WAV-Daten abgeschnitten.");
                    if (id == "fmt ") {
                        if (length < 16) throw new InvalidDataException("WAV-Format ungueltig.");
                        format = reader.ReadUInt16(); channels = reader.ReadUInt16(); rate = reader.ReadUInt32();
                        uint bytesPerSecond = reader.ReadUInt32(); ushort block = reader.ReadUInt16(); bits = reader.ReadUInt16();
                        if (format != 1 || channels != 1 || rate != SampleRate || bits != 16 || block != 2 || bytesPerSecond != rate * 2)
                            throw new InvalidDataException("Referenz muss Mono-WAV mit 24 kHz und PCM16 sein.");
                    } else if (id == "data") { dataOffset = reader.BaseStream.Position; dataLength = length; }
                    reader.BaseStream.Position = next;
                }
                if (dataOffset < 0 || rate == 0 || dataLength == 0 || dataLength % 2 != 0) throw new InvalidDataException("WAV-Datei enthaelt keine Audiodaten.");
                reader.BaseStream.Position = dataOffset;
                long samples = dataLength / 2, clipped = 0;
                double sum = 0, squares = 0, peak = 0;
                for (long i = 0; i < samples; i++) {
                    double value = reader.ReadInt16() / 32768.0;
                    sum += value; squares += value * value; peak = Math.Max(peak, Math.Abs(value));
                    if (Math.Abs(value) >= 32700.0 / 32768.0) clipped++;
                }
                double mean = sum / samples;
                return new WavAnalysis { DurationSeconds = (double)samples / rate, SampleRate = (int)rate, Channels = channels,
                    Rms = Math.Sqrt(Math.Max(0, squares / samples - mean * mean)), Peak = peak, ClippedFraction = (double)clipped / samples };
            }
        }
    }
}
