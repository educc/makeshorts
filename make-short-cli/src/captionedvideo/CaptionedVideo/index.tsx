import { Caption, createTikTokStyleCaptions } from "@remotion/captions";
import { getVideoMetadata } from "@remotion/media-utils";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AbsoluteFill,
  CalculateMetadataFunction,
  cancelRender,
  getRemotionEnvironment,
  OffthreadVideo,
  Sequence,
  useDelayRender,
  useVideoConfig,
  watchStaticFile,
} from "remotion";
import { z } from "zod";
import { loadFont } from "../load-font";
import { NoCaptionFile } from "./NoCaptionFile";
import SubtitlePage from "./SubtitlePage";

export type SubtitleProp = {
  startInSeconds: number;
  text: string;
};

export const captionedVideoSchema = z.object({
  src: z.string(),
});

export const calculateCaptionedVideoMetadata: CalculateMetadataFunction<
  z.infer<typeof captionedVideoSchema>
> = async ({ props }) => {
  const fps = 30;
  try {
    const metadata = await getVideoMetadata(props.src);

    return {
      fps,
      durationInFrames: Math.floor(metadata.durationInSeconds * fps),
    };
  } catch {
    return {
      fps,
      durationInFrames: fps,
    };
  }
};

// How many captions should be displayed at a time?
// Try out:
// - 1500 to display a lot of words at a time
// - 200 to only display 1 word at a time
const SWITCH_CAPTIONS_EVERY_MS = 1200;

export const CaptionedVideo: React.FC<{
  src: string;
}> = ({ src }) => {
  const [subtitles, setSubtitles] = useState<Caption[]>([]);
  const [subtitleFound, setSubtitleFound] = useState(true);
  const { delayRender, continueRender } = useDelayRender();
  const [handle] = useState(() => delayRender());
  const { fps } = useVideoConfig();

  const subtitlesFile = src
    .replace(/.mp4$/, ".json")
    .replace(/.mkv$/, ".json")
    .replace(/.mov$/, ".json")
    .replace(/.webm$/, ".json");

  const fetchSubtitles = useCallback(async () => {
    try {
      await loadFont();
      const res = await fetch(subtitlesFile);
      if (!res.ok) {
        setSubtitles([]);
        setSubtitleFound(false);
        return;
      }

      const data = (await res.json()) as unknown;
      if (!Array.isArray(data)) {
        setSubtitles([]);
        setSubtitleFound(false);
        return;
      }

      setSubtitles(data as Caption[]);
      setSubtitleFound(true);
    } catch {
      setSubtitles([]);
      setSubtitleFound(false);
    } finally {
      continueRender(handle);
    }
  }, [continueRender, handle, subtitlesFile]);

  useEffect(() => {
    const { isStudio } = getRemotionEnvironment();

    fetchSubtitles().catch((err) => {
      cancelRender(err);
    });

    if (!isStudio) {
      return;
    }

    const watcher = watchStaticFile(subtitlesFile, () => {
      fetchSubtitles().catch((err) => {
        cancelRender(err);
      });
    });

    return () => {
      watcher.cancel();
    };
  }, [fetchSubtitles, subtitlesFile]);

  const { pages } = useMemo(() => {
    return createTikTokStyleCaptions({
      combineTokensWithinMilliseconds: SWITCH_CAPTIONS_EVERY_MS,
      captions: subtitles ?? [],
    });
  }, [subtitles]);

  return (
    <AbsoluteFill style={{ backgroundColor: "white" }}>
      <AbsoluteFill>
        <OffthreadVideo
          style={{
            objectFit: "cover",
          }}
          src={src}
        />
      </AbsoluteFill>
      {pages.map((page, index) => {
        const nextPage = pages[index + 1] ?? null;
        const subtitleStartFrame = (page.startMs / 1000) * fps;
        const subtitleEndFrame = Math.min(
          nextPage ? (nextPage.startMs / 1000) * fps : Infinity,
          subtitleStartFrame + SWITCH_CAPTIONS_EVERY_MS,
        );
        const durationInFrames = subtitleEndFrame - subtitleStartFrame;
        if (durationInFrames <= 0) {
          return null;
        }

        return (
          <Sequence
            key={index}
            from={subtitleStartFrame}
            durationInFrames={durationInFrames}
          >
            <SubtitlePage key={index} page={page} />;
          </Sequence>
        );
      })}
      {subtitleFound ? null : <NoCaptionFile />}
    </AbsoluteFill>
  );
};
