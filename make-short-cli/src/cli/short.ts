import {
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";

type SubtitleCaption = {
  text: string;
  startMs: number;
  endMs: number;
  timestampMs: number | null;
  confidence: number;
};

type TranscriptChunk = {
  id: number;
  startMs: number;
  endMs: number;
  text: string;
};

type ShortSelection = {
  startChunkId: number;
  endChunkId: number;
  viralityScore: number;
  hook: string;
  reason: string;
};

type EvaluatedSelection = ShortSelection & {
  iteration: number;
  startMs: number;
  endMs: number;
  durationSec: number;
  normalizedScore: number;
};

const DEFAULT_SECONDS = 20;
const MAX_ITERATIONS = 10;
const DEFAULT_OPENAI_BASE_URL = "http://localhost:3009";
const DEFAULT_OPENAI_MODEL = "gpt-5-mini";

const SYSTEM_PROMPT = `You are an elite short-form video editor and viral content strategist.

Your job is to pick ONE contiguous subtitle range that will become a short video for TikTok, YouTube Shorts, and Instagram Reels.

Primary objective:
- Maximize retention and shareability.

Hard constraints:
- Return a range between startChunkId and endChunkId (inclusive).
- The selected duration must be <= targetSeconds.
- The range must be contiguous.

Selection principles:
- Prefer moments with a strong hook in the first 1-2 seconds.
- Prefer emotional spikes, surprise, tension, payoff, social proof, or clear transformation.
- Prefer standalone clarity when watched out of context.
- Avoid long low-energy build-up.
- Prefer natural language cadence and coherent sentence boundaries.
- If multiple candidates are close, favor the one that is easier to understand instantly and likely to spark comments/shares.

Optimization behavior:
- You may receive previous attempts and a current best score.
- Propose a better range when possible.
- Be strict and realistic with viralityScore (0-100).

Output rules:
- Return valid JSON only.
- Follow the required schema exactly.
- Do not include markdown, prose outside JSON, or extra keys.`;

const isFiniteNumber = (value: unknown): value is number => {
  return typeof value === "number" && Number.isFinite(value);
};

const usage = () => {
  return "Usage: bun src/cli/short.ts <subtitle-json-file> [--seconds <number>] [--model <name>] [--max-iterations <1-10>]";
};

const parseArgs = (args: string[]) => {
  let filenameArg: string | null = null;
  let seconds = DEFAULT_SECONDS;
  let modelArg: string | null = null;
  let maxIterations = MAX_ITERATIONS;

  for (let index = 0; index < args.length; index++) {
    const arg = args[index];

    if (arg === "--seconds") {
      const value = args[index + 1];
      if (!value || value.startsWith("--")) {
        throw new Error("Missing value for --seconds.");
      }

      const parsed = Number(value);
      if (!Number.isFinite(parsed) || parsed <= 0) {
        throw new Error("--seconds must be a positive number.");
      }

      seconds = parsed;
      index += 1;
      continue;
    }

    if (arg.startsWith("--seconds=")) {
      const rawValue = arg.slice("--seconds=".length);
      const parsed = Number(rawValue);
      if (!rawValue || !Number.isFinite(parsed) || parsed <= 0) {
        throw new Error("--seconds must be a positive number.");
      }

      seconds = parsed;
      continue;
    }

    if (arg === "--model") {
      const value = args[index + 1];
      if (!value || value.startsWith("--")) {
        throw new Error("Missing value for --model.");
      }

      if (value.trim().length === 0) {
        throw new Error("--model must be a non-empty string.");
      }

      modelArg = value.trim();
      index += 1;
      continue;
    }

    if (arg.startsWith("--model=")) {
      const value = arg.slice("--model=".length).trim();
      if (!value) {
        throw new Error("--model must be a non-empty string.");
      }

      modelArg = value;
      continue;
    }

    if (arg === "--max-iterations") {
      const value = args[index + 1];
      if (!value || value.startsWith("--")) {
        throw new Error("Missing value for --max-iterations.");
      }

      const parsed = Number(value);
      if (!Number.isInteger(parsed) || parsed < 1 || parsed > MAX_ITERATIONS) {
        throw new Error(
          `--max-iterations must be an integer between 1 and ${MAX_ITERATIONS}.`,
        );
      }

      maxIterations = parsed;
      index += 1;
      continue;
    }

    if (arg.startsWith("--max-iterations=")) {
      const rawValue = arg.slice("--max-iterations=".length);
      const parsed = Number(rawValue);
      if (!Number.isInteger(parsed) || parsed < 1 || parsed > MAX_ITERATIONS) {
        throw new Error(
          `--max-iterations must be an integer between 1 and ${MAX_ITERATIONS}.`,
        );
      }

      maxIterations = parsed;
      continue;
    }

    if (arg.startsWith("--")) {
      throw new Error(`Unknown option: ${arg}`);
    }

    if (filenameArg) {
      throw new Error(`Unexpected argument: ${arg}`);
    }

    filenameArg = arg;
  }

  if (!filenameArg) {
    throw new Error(usage());
  }

  return {
    filenameArg,
    seconds,
    modelArg,
    maxIterations,
  };
};

const resolveSubtitleJson = (filenameArg: string) => {
  const subtitlePath = path.resolve(process.cwd(), filenameArg);

  if (!existsSync(subtitlePath)) {
    throw new Error(`Subtitle JSON file not found: ${subtitlePath}`);
  }

  const stat = lstatSync(subtitlePath);
  if (stat.isDirectory()) {
    throw new Error(`Expected a file but got a directory: ${subtitlePath}`);
  }

  if (path.extname(subtitlePath).toLowerCase() !== ".json") {
    throw new Error(`Subtitle file must be a .json file: ${subtitlePath}`);
  }

  return subtitlePath;
};

const validateSubtitleJson = (subtitleJsonPath: string): SubtitleCaption[] => {
  let parsed: unknown;
  try {
    parsed = JSON.parse(readFileSync(subtitleJsonPath, "utf8"));
  } catch {
    throw new Error(`Subtitle JSON is not valid JSON: ${subtitleJsonPath}`);
  }

  if (!Array.isArray(parsed)) {
    throw new Error(
      `Invalid subtitle JSON format in ${subtitleJsonPath}. Expected an array of captions.`,
    );
  }

  const captions = parsed.map((entry, index) => {
    if (typeof entry !== "object" || entry === null || Array.isArray(entry)) {
      throw new Error(
        `Invalid caption at index ${index} in ${subtitleJsonPath}. Expected an object.`,
      );
    }

    const caption = entry as Record<string, unknown>;
    if (typeof caption.text !== "string") {
      throw new Error(
        `Invalid caption.text at index ${index} in ${subtitleJsonPath}. Expected a string.`,
      );
    }
    if (!isFiniteNumber(caption.startMs)) {
      throw new Error(
        `Invalid caption.startMs at index ${index} in ${subtitleJsonPath}. Expected a number.`,
      );
    }
    if (!isFiniteNumber(caption.endMs)) {
      throw new Error(
        `Invalid caption.endMs at index ${index} in ${subtitleJsonPath}. Expected a number.`,
      );
    }
    if (caption.timestampMs !== null && !isFiniteNumber(caption.timestampMs)) {
      throw new Error(
        `Invalid caption.timestampMs at index ${index} in ${subtitleJsonPath}. Expected a number or null.`,
      );
    }
    if (!isFiniteNumber(caption.confidence)) {
      throw new Error(
        `Invalid caption.confidence at index ${index} in ${subtitleJsonPath}. Expected a number.`,
      );
    }
    if (caption.endMs < caption.startMs) {
      throw new Error(
        `Invalid caption range at index ${index} in ${subtitleJsonPath}. endMs must be >= startMs.`,
      );
    }

    return {
      text: caption.text,
      startMs: caption.startMs,
      endMs: caption.endMs,
      timestampMs: caption.timestampMs,
      confidence: caption.confidence,
    };
  });

  if (captions.length === 0) {
    throw new Error(`Subtitle JSON has no captions: ${subtitleJsonPath}`);
  }

  return captions;
};

const normalizeToken = (text: string) => {
  return text.replace(/\s+/g, " ").trim();
};

const getWordCount = (text: string) => {
  return text
    .trim()
    .split(/\s+/)
    .filter((part) => part.length > 0).length;
};

const buildTranscriptChunks = (
  captions: SubtitleCaption[],
): TranscriptChunk[] => {
  const chunks: TranscriptChunk[] = [];

  let currentTextParts: string[] = [];
  let currentStartMs = 0;
  let currentEndMs = 0;
  let currentWordCount = 0;
  let hasOpenChunk = false;

  const closeChunk = () => {
    if (!hasOpenChunk) {
      return;
    }

    const text = currentTextParts.join(" ").replace(/\s+/g, " ").trim();
    if (text.length > 0) {
      chunks.push({
        id: chunks.length,
        startMs: currentStartMs,
        endMs: currentEndMs,
        text,
      });
    }

    currentTextParts = [];
    currentWordCount = 0;
    hasOpenChunk = false;
  };

  for (let index = 0; index < captions.length; index++) {
    const caption = captions[index];
    const token = normalizeToken(caption.text);
    if (token.length === 0) {
      continue;
    }

    if (!hasOpenChunk) {
      currentStartMs = caption.startMs;
      currentEndMs = caption.endMs;
      currentTextParts = [token];
      currentWordCount = getWordCount(token);
      hasOpenChunk = true;
    } else {
      currentTextParts.push(token);
      currentEndMs = caption.endMs;
      currentWordCount += getWordCount(token);
    }

    const nextCaption = captions[index + 1] ?? null;
    const gapToNext = nextCaption
      ? nextCaption.startMs - caption.endMs
      : Infinity;
    const chunkDuration = currentEndMs - currentStartMs;
    const punctuationBoundary = /[.!?]$/.test(token);
    const gapBoundary = gapToNext > 650;
    const maxDurationBoundary = chunkDuration >= 4200;
    const maxWordsBoundary = currentWordCount >= 18;

    if (
      !nextCaption ||
      punctuationBoundary ||
      gapBoundary ||
      maxDurationBoundary ||
      maxWordsBoundary
    ) {
      closeChunk();
    }
  }

  closeChunk();

  if (chunks.length === 0) {
    throw new Error(
      "Could not build transcript chunks from the subtitle file.",
    );
  }

  return chunks;
};

const formatChunksForPrompt = (chunks: TranscriptChunk[]) => {
  return chunks
    .map((chunk) => {
      return `#${chunk.id} [${chunk.startMs}-${chunk.endMs}] ${chunk.text}`;
    })
    .join("\n");
};

const buildJsonSchemaResponseFormat = () => {
  return {
    type: "json_schema",
    json_schema: {
      name: "viral_short_selection",
      strict: true,
      schema: {
        type: "object",
        additionalProperties: false,
        required: [
          "startChunkId",
          "endChunkId",
          "viralityScore",
          "hook",
          "reason",
        ],
        properties: {
          startChunkId: { type: "integer" },
          endChunkId: { type: "integer" },
          viralityScore: { type: "number", minimum: 0, maximum: 100 },
          hook: { type: "string", minLength: 1 },
          reason: { type: "string", minLength: 1 },
        },
      },
    },
  };
};

const extractApiErrorMessage = (raw: string) => {
  try {
    const parsed = JSON.parse(raw) as {
      error?: { message?: string };
      message?: string;
    };
    if (parsed.error?.message) {
      return parsed.error.message;
    }
    if (parsed.message) {
      return parsed.message;
    }
  } catch {
    // noop
  }

  return raw;
};

const extractContentFromChatCompletion = (payload: unknown): string => {
  if (
    typeof payload !== "object" ||
    payload === null ||
    Array.isArray(payload)
  ) {
    throw new Error("Invalid OpenAI response format.");
  }

  const root = payload as Record<string, unknown>;
  if (!Array.isArray(root.choices) || root.choices.length === 0) {
    throw new Error("OpenAI response does not include choices.");
  }

  const firstChoice = root.choices[0];
  if (
    typeof firstChoice !== "object" ||
    firstChoice === null ||
    Array.isArray(firstChoice)
  ) {
    throw new Error("OpenAI response choice is invalid.");
  }

  const choice = firstChoice as Record<string, unknown>;
  const message = choice.message;
  if (
    typeof message !== "object" ||
    message === null ||
    Array.isArray(message)
  ) {
    throw new Error("OpenAI response choice has no message.");
  }

  const content = (message as Record<string, unknown>).content;
  if (typeof content === "string") {
    return content;
  }

  if (Array.isArray(content)) {
    const textParts = content
      .map((part) => {
        if (typeof part === "string") {
          return part;
        }

        if (typeof part !== "object" || part === null || Array.isArray(part)) {
          return "";
        }

        const record = part as Record<string, unknown>;
        if (typeof record.text === "string") {
          return record.text;
        }

        return "";
      })
      .filter((part) => part.length > 0);

    if (textParts.length > 0) {
      return textParts.join("\n");
    }
  }

  throw new Error("OpenAI response has no readable message content.");
};

const stripCodeFence = (value: string) => {
  const trimmed = value.trim();
  const match = trimmed.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  if (!match) {
    return trimmed;
  }
  return match[1].trim();
};

const parseSelection = (rawContent: string): ShortSelection => {
  const json = stripCodeFence(rawContent);

  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch {
    throw new Error(`Model response is not valid JSON: ${rawContent}`);
  }

  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("Model response must be a JSON object.");
  }

  const record = parsed as Record<string, unknown>;
  const startChunkId = record.startChunkId;
  const endChunkId = record.endChunkId;
  const viralityScore = record.viralityScore;
  const hook = record.hook;
  const reason = record.reason;

  if (!Number.isInteger(startChunkId)) {
    throw new Error("startChunkId must be an integer.");
  }
  if (!Number.isInteger(endChunkId)) {
    throw new Error("endChunkId must be an integer.");
  }
  if (!isFiniteNumber(viralityScore)) {
    throw new Error("viralityScore must be a finite number.");
  }
  if (typeof hook !== "string" || hook.trim().length === 0) {
    throw new Error("hook must be a non-empty string.");
  }
  if (typeof reason !== "string" || reason.trim().length === 0) {
    throw new Error("reason must be a non-empty string.");
  }

  const safeStartChunkId = Number(startChunkId);
  const safeEndChunkId = Number(endChunkId);

  return {
    startChunkId: safeStartChunkId,
    endChunkId: safeEndChunkId,
    viralityScore,
    hook: hook.trim(),
    reason: reason.trim(),
  };
};

const evaluateSelection = (
  selection: ShortSelection,
  chunks: TranscriptChunk[],
  targetSeconds: number,
  iteration: number,
): EvaluatedSelection => {
  if (selection.startChunkId < 0 || selection.startChunkId >= chunks.length) {
    throw new Error(
      `startChunkId ${selection.startChunkId} is out of bounds for ${chunks.length} chunks.`,
    );
  }

  if (selection.endChunkId < 0 || selection.endChunkId >= chunks.length) {
    throw new Error(
      `endChunkId ${selection.endChunkId} is out of bounds for ${chunks.length} chunks.`,
    );
  }

  if (selection.endChunkId < selection.startChunkId) {
    throw new Error("endChunkId must be >= startChunkId.");
  }

  const startMs = chunks[selection.startChunkId].startMs;
  const endMs = chunks[selection.endChunkId].endMs;
  if (endMs <= startMs) {
    throw new Error("Selected range has invalid timestamps.");
  }

  const durationSec = (endMs - startMs) / 1000;
  if (durationSec > targetSeconds) {
    throw new Error(
      `Selected duration ${durationSec.toFixed(2)}s exceeds target ${targetSeconds}s.`,
    );
  }

  const boundedViralityScore = Math.max(
    0,
    Math.min(100, selection.viralityScore),
  );
  const utilizationBonus = Math.min(10, (durationSec / targetSeconds) * 10);
  const normalizedScore = boundedViralityScore + utilizationBonus;

  return {
    ...selection,
    iteration,
    startMs,
    endMs,
    durationSec,
    normalizedScore,
  };
};

const buildUserPrompt = (
  chunksPrompt: string,
  targetSeconds: number,
  best: EvaluatedSelection | null,
  feedback: string,
) => {
  const bestSnapshot = best
    ? `Current best: chunks ${best.startChunkId}-${best.endChunkId}, duration ${best.durationSec.toFixed(2)}s, normalizedScore ${best.normalizedScore.toFixed(2)}, viralityScore ${best.viralityScore.toFixed(2)}, hook "${best.hook}"`
    : "Current best: none yet.";

  return [
    `targetSeconds: ${targetSeconds}`,
    bestSnapshot,
    `Feedback from previous attempt: ${feedback}`,
    "Return only JSON that matches the schema.",
    "Transcript chunks:",
    chunksPrompt,
  ].join("\n\n");
};

const createCompletion = async (
  endpoint: string,
  apiKey: string | null,
  model: string,
  systemPrompt: string,
  userPrompt: string,
  useJsonSchema: boolean,
) => {
  const requestBody: Record<string, unknown> = {
    model,
    temperature: 0.2,
    max_completion_tokens: 500,
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: userPrompt },
    ],
  };

  if (useJsonSchema) {
    requestBody.response_format = buildJsonSchemaResponseFormat();
  } else {
    requestBody.response_format = {
      type: "json_object",
    };
  }

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (apiKey) {
    headers.Authorization = `Bearer ${apiKey}`;
  }

  const response = await fetch(endpoint, {
    method: "POST",
    headers,
    body: JSON.stringify(requestBody),
  });

  const rawBody = await response.text();
  if (!response.ok) {
    throw new Error(
      `OpenAI API request failed (${response.status}): ${extractApiErrorMessage(rawBody)}`,
    );
  }

  let payload: unknown;
  try {
    payload = JSON.parse(rawBody);
  } catch {
    throw new Error(`OpenAI API returned non-JSON response: ${rawBody}`);
  }

  return extractContentFromChatCompletion(payload);
};

const requestSelectionFromOpenAi = async (
  endpoint: string,
  apiKey: string | null,
  model: string,
  systemPrompt: string,
  userPrompt: string,
) => {
  try {
    return await createCompletion(
      endpoint,
      apiKey,
      model,
      systemPrompt,
      userPrompt,
      true,
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const schemaLikelyUnsupported =
      message.includes("json_schema") ||
      message.includes("response_format") ||
      message.includes("Unsupported value");

    if (!schemaLikelyUnsupported) {
      throw error;
    }

    return createCompletion(
      endpoint,
      apiKey,
      model,
      systemPrompt,
      userPrompt,
      false,
    );
  }
};

const formatSecondsForFileName = (seconds: number) => {
  const rounded = Number(seconds.toFixed(3));
  if (Number.isInteger(rounded)) {
    return `${rounded}`;
  }

  return `${rounded}`.replace(".", "_");
};

const ensureOpenAiEndpoint = (modelArg: string | null) => {
  const baseUrlRaw = process.env.OPENAI_BASE_URL ?? DEFAULT_OPENAI_BASE_URL;
  let parsed: URL;
  try {
    parsed = new URL(baseUrlRaw);
  } catch {
    throw new Error(`Invalid OPENAI_BASE_URL: ${baseUrlRaw}`);
  }

  const model =
    modelArg ??
    process.env.OPENAI_SHORT_MODEL ??
    process.env.OPENAI_MODEL ??
    DEFAULT_OPENAI_MODEL;
  const apiKey = process.env.OPENAI_API_KEY ?? null;
  if (parsed.hostname === "api.openai.com" && !apiKey) {
    throw new Error(
      "OPENAI_API_KEY is required when OPENAI_BASE_URL points to api.openai.com.",
    );
  }

  const endpoint = new URL("/v1/chat/completions", parsed).toString();
  return { endpoint, apiKey, model, baseUrlRaw };
};

const main = async () => {
  const { filenameArg, seconds, modelArg, maxIterations } = parseArgs(
    process.argv.slice(2),
  );
  const subtitlePath = resolveSubtitleJson(filenameArg);
  const captions = validateSubtitleJson(subtitlePath);
  const chunks = buildTranscriptChunks(captions);
  const chunksPrompt = formatChunksForPrompt(chunks);

  const { endpoint, apiKey, model, baseUrlRaw } =
    ensureOpenAiEndpoint(modelArg);

  let bestSelection: EvaluatedSelection | null = null;
  let feedback = "No previous attempts yet.";
  let roundsWithoutImprovement = 0;

  for (let iteration = 1; iteration <= maxIterations; iteration++) {
    const userPrompt = buildUserPrompt(
      chunksPrompt,
      seconds,
      bestSelection,
      feedback,
    );

    try {
      const rawContent = await requestSelectionFromOpenAi(
        endpoint,
        apiKey,
        model,
        SYSTEM_PROMPT,
        userPrompt,
      );
      const parsedSelection = parseSelection(rawContent);
      const evaluated = evaluateSelection(
        parsedSelection,
        chunks,
        seconds,
        iteration,
      );

      if (
        !bestSelection ||
        evaluated.normalizedScore > bestSelection.normalizedScore
      ) {
        bestSelection = evaluated;
        roundsWithoutImprovement = 0;
        feedback = `Accepted. Improve this benchmark: normalizedScore=${evaluated.normalizedScore.toFixed(2)}, duration=${evaluated.durationSec.toFixed(2)}s, hook=${evaluated.hook}`;
      } else {
        roundsWithoutImprovement += 1;
        feedback = `Rejected. Candidate score ${evaluated.normalizedScore.toFixed(2)} was not better than best ${bestSelection.normalizedScore.toFixed(2)}.`;
      }
    } catch (error) {
      roundsWithoutImprovement += 1;
      const message = error instanceof Error ? error.message : String(error);
      feedback = `Invalid attempt. Fix all issues and return valid JSON. Error: ${message}`;
    }

    if (iteration >= 3 && roundsWithoutImprovement >= 3 && bestSelection) {
      break;
    }
  }

  if (!bestSelection) {
    throw new Error(
      `Could not produce a valid short after ${maxIterations} iterations. Check OpenAI connectivity and model compatibility at ${baseUrlRaw}.`,
    );
  }

  const selectedCaptions = captions.filter((caption) => {
    return (
      caption.endMs > bestSelection.startMs &&
      caption.startMs < bestSelection.endMs
    );
  });

  if (selectedCaptions.length === 0) {
    throw new Error("The selected short has no captions after filtering.");
  }

  const inputBaseName = path.basename(subtitlePath, ".json");
  const secondsLabel = formatSecondsForFileName(seconds);
  const publicDir = path.join(process.cwd(), "public");
  mkdirSync(publicDir, { recursive: true });
  const outputPath = path.join(
    publicDir,
    `${inputBaseName}_${secondsLabel}s.json`,
  );

  writeFileSync(outputPath, JSON.stringify(selectedCaptions, null, 2));

  console.log(`Input subtitle JSON: ${subtitlePath}`);
  console.log(`LLM chunks analyzed: ${chunks.length}`);
  console.log(`Model: ${model}`);
  console.log(`Max iterations: ${maxIterations}`);
  console.log(`Target short duration: ${seconds}s`);
  console.log(
    `Selected range: ${bestSelection.startMs}ms - ${bestSelection.endMs}ms (${bestSelection.durationSec.toFixed(2)}s)`,
  );
  console.log(`Selected hook: ${bestSelection.hook}`);
  console.log(`Selection reason: ${bestSelection.reason}`);
  console.log(`Selection score: ${bestSelection.normalizedScore.toFixed(2)}`);
  console.log(`Output captions: ${selectedCaptions.length}`);
  console.log(`Saved short subtitle JSON: ${outputPath}`);
};

void main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : String(error);
  console.error(message);
  console.error(usage());
  process.exit(1);
});
