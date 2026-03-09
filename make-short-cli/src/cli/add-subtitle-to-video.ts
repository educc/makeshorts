import { spawnSync } from "node:child_process";
import { cpSync, existsSync, lstatSync, mkdirSync, rmSync } from "node:fs";
import path from "node:path";

const SUPPORTED_EXTENSIONS = new Set([".mp4", ".webm", ".mkv", ".mov"]);

const run = (command: string, args: string[]) => {
  const result = spawnSync(command, args, {
    cwd: process.cwd(),
    stdio: "inherit",
  });

  if (result.status !== 0) {
    throw new Error(`Command failed: ${command} ${args.join(" ")}`);
  }
};

const cleanDirectory = (directoryPath: string) => {
  rmSync(directoryPath, { recursive: true, force: true });
  mkdirSync(directoryPath, { recursive: true });
};

const isPathInside = (targetPath: string, parentPath: string) => {
  const relative = path.relative(parentPath, targetPath);
  return (
    relative !== "" && !relative.startsWith("..") && !path.isAbsolute(relative)
  );
};

const resolveInputVideo = (videoArg: string) => {
  const videoPath = path.resolve(process.cwd(), videoArg);

  if (!existsSync(videoPath)) {
    throw new Error(`Video file not found: ${videoPath}`);
  }

  const stat = lstatSync(videoPath);
  if (stat.isDirectory()) {
    throw new Error(`Expected a file but got a directory: ${videoPath}`);
  }

  const extension = path.extname(videoPath).toLowerCase();
  if (!SUPPORTED_EXTENSIONS.has(extension)) {
    throw new Error(
      `Unsupported extension "${extension}". Use: ${Array.from(SUPPORTED_EXTENSIONS).join(", ")}`,
    );
  }

  return videoPath;
};

const main = async () => {
  const videoArg = process.argv[2];
  if (!videoArg) {
    throw new Error(
      "Usage: bun src/cli/add-subtitle-to-video.ts <path-to-video>",
    );
  }

  const inputVideoPath = resolveInputVideo(videoArg);
  const fileName = path.basename(inputVideoPath);
  const fileNameWithoutExt = path.basename(
    inputVideoPath,
    path.extname(inputVideoPath),
  );

  const publicDir = path.join(process.cwd(), "public");
  const outDir = path.join(process.cwd(), "out");

  if (isPathInside(inputVideoPath, publicDir)) {
    throw new Error(
      "Input video cannot be inside public/, because public/ is cleaned before each run.",
    );
  }

  cleanDirectory(publicDir);
  mkdirSync(outDir, { recursive: true });

  const publicVideoPath = path.join(publicDir, fileName);
  cpSync(inputVideoPath, publicVideoPath);

  run("bun", ["run", "create-subtitles", publicVideoPath]);

  const subtitleJsonPath = path.join(outDir, `${fileNameWithoutExt}.json`);
  if (!existsSync(subtitleJsonPath)) {
    throw new Error(`Subtitle JSON was not created: ${subtitleJsonPath}`);
  }

  const subtitleJsonPublicPath = path.join(
    publicDir,
    `${fileNameWithoutExt}.json`,
  );
  cpSync(subtitleJsonPath, subtitleJsonPublicPath);

  const outputVideoPath = path.join(
    outDir,
    `${fileNameWithoutExt}-captioned.mp4`,
  );
  run("bun", [
    "run",
    "render",
    "CaptionedVideo",
    outputVideoPath,
    `--props=${JSON.stringify({ src: `/public/${fileName}` })}`,
  ]);

  console.log(`Cleaned public directory: ${publicDir}`);
  console.log(`Created subtitle JSON: ${subtitleJsonPath}`);
  console.log(`Copied subtitle JSON: ${subtitleJsonPublicPath}`);
  console.log(`Created captioned video: ${outputVideoPath}`);
};

void main().catch((err: unknown) => {
  const message = err instanceof Error ? err.message : String(err);
  console.error(message);
  process.exit(1);
});
