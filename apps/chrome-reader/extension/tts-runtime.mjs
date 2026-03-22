import { Language } from "./vendor/headtts/language-en-us.mjs";
import { encodeAudio } from "./vendor/headtts/utils.mjs";

const SAMPLE_RATE = 24000;
const STYLE_DIM = 256;
const MAX_TEXT_TOKENS = 2048;
const MAX_MODEL_TOKENS = 511;
const MAX_SPLIT_DEPTH = 8;
const PAD_TOKEN_ID = 0;
const SPLIT_GAP_MS = 80;
const ORT_ENTRY_PATHS = {
  wasm: "./vendor/onnxruntime/ort.wasm.min.mjs",
  webgpu: "./vendor/onnxruntime/ort.webgpu.min.mjs",
};
// Directory prefix for ONNX Runtime WASM files.
// ort.env.wasm.wasmPaths accepts a URL prefix string; ONNX Runtime appends the
// expected filename (e.g. "ort-wasm-simd-threaded.wasm") automatically.
const ORT_WASM_DIR = new URL("./vendor/onnxruntime/", import.meta.url).href;
const DEFAULT_STATUS = {
  ready: false,
  status: "idle",
  device: "uninitialized",
  deviceLabel: "Not loaded",
  message: "Local Kokoro loads on first play",
  error: null,
};

let session = null;
let ortRuntime = null;
let tokenizerVocab = null;
let language = null;
let engineDevice = "uninitialized";
let currentGeneration = 0;
let initPromise = null;
let processing = false;
const queue = [];
const voiceCache = new Map();
const ortModuleCache = new Map();
const statusListeners = new Set();
let statusState = { ...DEFAULT_STATUS };

function assetUrl(relativePath) {
  return new URL(relativePath, import.meta.url).href;
}

function deviceLabel(device) {
  if (device === "webgpu") return "GPU";
  if (device === "wasm") return "CPU/WASM";
  if (device === "unavailable") return "Unavailable";
  return "Not loaded";
}

function errorMessage(error) {
  return error?.message || String(error) || "Unknown error";
}

function emitStatus() {
  const snapshot = getStatus();
  for (const listener of statusListeners) {
    try {
      listener(snapshot);
    } catch (_) {
      // Listener failures should not break synthesis.
    }
  }
}

function updateStatus(partial = {}) {
  statusState = {
    ...statusState,
    ...partial,
    device: partial.device || statusState.device,
    deviceLabel: deviceLabel(partial.device || statusState.device),
    error:
      partial.status === "error"
        ? partial.error || partial.message || statusState.error
        : partial.error ?? null,
  };
  emitStatus();
}

async function loadTokenizer() {
  if (tokenizerVocab) return tokenizerVocab;

  const response = await fetch(assetUrl("./models/kokoro/tokenizer.json"));
  if (!response.ok) {
    throw new Error("Tokenizer metadata is missing from the extension package");
  }

  const tokenizer = await response.json();
  tokenizerVocab = tokenizer?.model?.vocab || null;
  if (!tokenizerVocab) {
    throw new Error("Tokenizer vocabulary is invalid");
  }

  return tokenizerVocab;
}

async function loadLanguage() {
  if (language) return language;
  language = new Language({ trace: false });
  await language.loadDictionary(assetUrl("./vendor/headtts/dictionaries/en-us.txt"));
  return language;
}

async function loadVoice(voice) {
  if (voiceCache.has(voice)) {
    return voiceCache.get(voice);
  }

  const response = await fetch(assetUrl(`./models/kokoro/voices/${voice}.bin`));
  if (!response.ok) {
    throw new Error(`Voice "${voice}" is not packaged with the extension`);
  }

  const voiceData = new Float32Array(await response.arrayBuffer());
  voiceCache.set(voice, voiceData);
  return voiceData;
}

function tokenizePhonemes(phonemes, vocab) {
  const ids = [PAD_TOKEN_ID];
  for (const char of phonemes) {
    const id = vocab[char];
    if (id !== undefined) {
      ids.push(id);
    }
  }
  ids.push(PAD_TOKEN_ID);

  if (ids.length > MAX_TEXT_TOKENS) {
    ids.length = MAX_TEXT_TOKENS;
    ids[MAX_TEXT_TOKENS - 1] = PAD_TOKEN_ID;
  }

  return ids;
}

function buildStyleVector(voiceData, tokenCount) {
  const numTokens = Math.min(Math.max(tokenCount - 2, 0), 509);
  const offset = numTokens * STYLE_DIM;
  return voiceData.slice(offset, offset + STYLE_DIM);
}

function concatFloat32Arrays(chunks) {
  const totalLength = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const merged = new Float32Array(totalLength);
  let offset = 0;

  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }

  return merged;
}

function findSplitIndex(text) {
  const midpoint = Math.floor(text.length / 2);
  const splitPatterns = [/[,;:]\s+/g, /[)\]]\s+/g, /[-–—]\s+/g, /\s+/g];

  for (const pattern of splitPatterns) {
    let bestIndex = -1;
    let bestDistance = Number.POSITIVE_INFINITY;
    let match;

    pattern.lastIndex = 0;
    while ((match = pattern.exec(text)) !== null) {
      const index = match.index + match[0].length;
      if (index <= 0 || index >= text.length) continue;

      const distance = Math.abs(index - midpoint);
      if (distance < bestDistance) {
        bestDistance = distance;
        bestIndex = index;
      }
    }

    if (bestIndex !== -1) {
      return bestIndex;
    }
  }

  return -1;
}

function splitTextForModel(text) {
  const splitIndex = findSplitIndex(text);
  if (splitIndex === -1) {
    return null;
  }

  const leftText = text.slice(0, splitIndex).trimEnd();
  const rawRightText = text.slice(splitIndex);
  const rightText = rawRightText.trimStart();
  if (!leftText || !rightText) {
    return null;
  }

  return {
    leftText,
    rightText,
    rightOffset: splitIndex + (rawRightText.length - rightText.length),
  };
}

function samplesToDurationMs(samples) {
  return Math.round((samples.length / SAMPLE_RATE) * 1000);
}

function buildSynthesisChunk(text, samples) {
  const durationMs = samplesToDurationMs(samples);
  return {
    samples,
    duration_ms: durationMs,
    words: estimateWordTimings(text, durationMs),
  };
}

function mergeSynthesisChunks(left, right, rightCharOffset) {
  const gapSamples = Math.round((SPLIT_GAP_MS / 1000) * SAMPLE_RATE);
  const mergedSamples = concatFloat32Arrays([
    left.samples,
    new Float32Array(gapSamples),
    right.samples,
  ]);
  const rightTimeOffset = left.duration_ms + SPLIT_GAP_MS;

  return {
    samples: mergedSamples,
    duration_ms: samplesToDurationMs(mergedSamples),
    words: [
      ...left.words,
      ...right.words.map((word) => ({
        ...word,
        char_start: word.char_start + rightCharOffset,
        char_end: word.char_end + rightCharOffset,
        start_ms: word.start_ms + rightTimeOffset,
        end_ms: word.end_ms + rightTimeOffset,
      })),
    ],
  };
}

function estimateWordWeight(word) {
  const base = Array.from(word.replace(/\s+/g, "")).length || 1;
  const punctuation = (word.match(/[,:;.!?…]+$/) || [""])[0].length;
  return base + punctuation * 0.6;
}

function estimateWordTimings(text, durationMs) {
  const chunks = [];
  const matcher = /\S+/g;
  let match;
  let totalWeight = 0;

  while ((match = matcher.exec(text)) !== null) {
    const word = match[0];
    const weight = estimateWordWeight(word);
    chunks.push({
      word,
      char_start: match.index,
      char_end: match.index + word.length,
      weight,
    });
    totalWeight += weight;
  }

  let cursor = 0;
  return chunks.map((chunk, index) => {
    const span = totalWeight > 0 ? (durationMs * chunk.weight) / totalWeight : 0;
    const startMs = Math.round(cursor);
    cursor = index === chunks.length - 1 ? durationMs : cursor + span;
    const endMs = Math.max(startMs + 1, Math.round(cursor));
    return {
      word: chunk.word,
      char_start: chunk.char_start,
      char_end: chunk.char_end,
      start_ms: startMs,
      end_ms: endMs,
    };
  });
}

async function loadOrt(provider) {
  if (ortModuleCache.has(provider)) {
    return ortModuleCache.get(provider);
  }

  const entryPath = ORT_ENTRY_PATHS[provider];
  if (!entryPath) {
    throw new Error(`Unsupported ONNX Runtime provider "${provider}"`);
  }

  const ort = await import(entryPath);
  ortModuleCache.set(provider, ort);
  return ort;
}

function configureOrt(ort, provider) {
  ort.env.wasm.wasmPaths = ORT_WASM_DIR;
  ort.env.wasm.numThreads = 1;
  ort.env.wasm.proxy = false;
  ort.env.wasm.initTimeout = 30000;
  ort.env.logLevel = "warning";
}

async function createSessionForProvider(provider) {
  const ort = await loadOrt(provider);
  configureOrt(ort, provider);

  const createdSession = await ort.InferenceSession.create(assetUrl("./models/kokoro/kokoro.onnx"), {
    executionProviders: [provider],
    graphOptimizationLevel: "all",
  });

  return {
    ort,
    session: createdSession,
  };
}

async function initializeEngine() {
  await Promise.all([loadTokenizer(), loadLanguage()]);

  const candidates = typeof navigator !== "undefined" && navigator.gpu
    ? ["webgpu", "wasm"]
    : ["wasm"];

  const providerErrors = [];
  for (const provider of candidates) {
    try {
      updateStatus({
        ready: false,
        status: "loading",
        device: provider,
        message: provider === "webgpu"
          ? "Trying GPU inference..."
          : "Falling back to CPU/WASM inference...",
      });

      const created = await createSessionForProvider(provider);
      session = created.session;
      ortRuntime = created.ort;
      engineDevice = provider;
      updateStatus({
        ready: true,
        status: "ready",
        device: provider,
        message: `Using ${deviceLabel(provider)} inference`,
      });
      return getStatus();
    } catch (error) {
      providerErrors.push(`[${provider}] ${errorMessage(error)}`);
      session = null;
      ortRuntime = null;
    }
  }

  engineDevice = "unavailable";
  throw new Error(`Unable to initialize local Kokoro inference: ${providerErrors.join("; ")}`);
}

async function inferSamples(tokenIds, voiceData) {
  if (!ortRuntime) {
    throw new Error("ONNX Runtime is not initialized");
  }

  const styleVector = buildStyleVector(voiceData, tokenIds.length);
  const inputs = {
    tokens: new ortRuntime.Tensor(
      "int64",
      BigInt64Array.from(tokenIds, (id) => BigInt(id)),
      [1, tokenIds.length]
    ),
    style: new ortRuntime.Tensor("float32", styleVector, [1, STYLE_DIM]),
    speed: new ortRuntime.Tensor("float32", Float32Array.from([1.0]), [1]),
  };

  let outputs;
  try {
    outputs = await session.run(inputs);
  } catch (error) {
    throw new Error(
      `Local Kokoro inference failed for ${tokenIds.length} tokens: ${errorMessage(error)}`
    );
  }

  const audioTensor = outputs.audio || outputs.waveform || Object.values(outputs)[0];
  const audioLengthTensor =
    outputs.audio_length || outputs.lengths || Object.values(outputs)[1];

  if (!audioTensor?.data) {
    throw new Error("Model output did not include audio samples");
  }

  const samples = audioTensor.data instanceof Float32Array
    ? audioTensor.data
    : Float32Array.from(audioTensor.data);
  const rawLength = audioLengthTensor?.data?.[0];
  const sampleLength = rawLength !== undefined ? Number(rawLength) : samples.length;
  return samples.slice(0, Math.max(0, Math.min(samples.length, sampleLength)));
}

async function synthesizePreparedText(text, activeLanguage, vocab, voiceData, depth = 0) {
  const { phonemes } = activeLanguage.generate(text);
  const tokenIds = tokenizePhonemes(phonemes.join(""), vocab);

  if (tokenIds.length <= 2) {
    throw new Error("No pronounceable content in this sentence");
  }

  if (tokenIds.length > MAX_MODEL_TOKENS) {
    if (depth >= MAX_SPLIT_DEPTH) {
      throw new Error(
        `Sentence is too long for local Kokoro (${tokenIds.length} tokens after phonemization)`
      );
    }

    const split = splitTextForModel(text);
    if (!split) {
      throw new Error(
        `Sentence is too long for local Kokoro (${tokenIds.length} tokens after phonemization)`
      );
    }

    const left = await synthesizePreparedText(
      split.leftText,
      activeLanguage,
      vocab,
      voiceData,
      depth + 1
    );
    const right = await synthesizePreparedText(
      split.rightText,
      activeLanguage,
      vocab,
      voiceData,
      depth + 1
    );
    return mergeSynthesisChunks(left, right, split.rightOffset);
  }

  const samples = await inferSamples(tokenIds, voiceData);
  return buildSynthesisChunk(text, samples);
}

export async function initialize() {
  if (session) {
    return getStatus();
  }

  if (!initPromise) {
    updateStatus({
      ready: false,
      status: "loading",
      device: "uninitialized",
      message: "Loading local Kokoro model...",
      error: null,
    });

    initPromise = initializeEngine()
      .catch((error) => {
        session = null;
        ortRuntime = null;
        engineDevice = "unavailable";
        updateStatus({
          ready: false,
          status: "error",
          device: engineDevice,
          message: error.message,
          error: error.message,
        });
        throw error;
      })
      .finally(() => {
        initPromise = null;
      });
  }

  return initPromise;
}

async function synthesizeText(text, voice) {
  await initialize();

  const activeLanguage = await loadLanguage();
  const vocab = await loadTokenizer();
  const voiceData = await loadVoice(voice);
  const result = await synthesizePreparedText(text, activeLanguage, vocab, voiceData);
  const audio = encodeAudio(result.samples, SAMPLE_RATE, true);

  return {
    audio,
    duration_ms: result.duration_ms,
    words: result.words,
  };
}

function processQueue() {
  if (processing) return;
  processing = true;

  (async () => {
    while (queue.length > 0) {
      const job = queue.shift();
      if (!job || job.generation !== currentGeneration) {
        if (job) {
          job.reject(new Error("Synthesis cancelled"));
        }
        continue;
      }

      try {
        const result = await synthesizeText(job.text, job.voice);
        if (job.generation !== currentGeneration) {
          job.reject(new Error("Synthesis cancelled"));
          continue;
        }
        job.resolve(result);
      } catch (error) {
        job.reject(error);
      }
    }

    processing = false;
  })();
}

export function synthesize(text, voice = "af_heart") {
  const cleanText = (text || "").trim();
  if (!cleanText) {
    return Promise.reject(new Error("Empty text"));
  }

  return new Promise((resolve, reject) => {
    queue.push({
      text: cleanText,
      voice,
      generation: currentGeneration,
      resolve,
      reject,
    });
    processQueue();
  });
}

export function cancelAll() {
  currentGeneration++;
  while (queue.length > 0) {
    const job = queue.shift();
    job?.reject(new Error("Synthesis cancelled"));
  }
}

export function getStatus() {
  return { ...statusState };
}

export function subscribe(listener) {
  if (!listener) {
    return () => {};
  }

  statusListeners.add(listener);
  listener(getStatus());
  return () => {
    statusListeners.delete(listener);
  };
}
