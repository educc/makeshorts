import React from "react";
import { AbsoluteFill } from "remotion";

export const NoCaptionFile: React.FC = () => {
  return (
    <AbsoluteFill
      style={{
        height: "auto",
        width: "100%",
        backgroundColor: "white",
        fontSize: 50,
        padding: 30,
        top: undefined,
        fontFamily: "sans-serif",
      }}
    >
      No caption file found in the public folder. <br /> Run
      {" `bun run create-subtitles <path-to-video-file>` "}to generate one in
      {" `workdir/`."}
    </AbsoluteFill>
  );
};
