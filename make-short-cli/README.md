# Remotion video

This project comes from https://github.com/remotion-dev/template-tiktok

<p align="center">
  <a href="https://github.com/remotion-dev/logo">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://github.com/remotion-dev/logo/raw/main/animated-logo-banner-dark.apng">
      <img alt="Animated Remotion Logo" src="https://github.com/remotion-dev/logo/raw/main/animated-logo-banner-light.gif">
    </picture>
  </a>
</p>

Welcome to your Remotion project!

## Commands

**Install Dependencies**

```console
bun install
```

**Start Preview**

```console
bun run dev
```

**Render video**

```console
bun run render
```

**Upgrade Remotion**

```console
bun run upgrade
```

## Captioning

Generate subtitles from a video and write the output JSON to `out/`.

```console
bun run create-subtitles <path-to-video-file>
```

Example using one of the repository test videos:

```console
bun run create-subtitles ./examples/winner01.mp4
```

Generate subtitles and render a captioned output video in one command:

```console
bun run add-subtitle-to-video ./examples/winner01.mp4
```

This command creates:

- `out/<video-name>.json`
- `out/<video-name>-captioned.mp4`

Before rendering, it cleans `public/` and copies the required runtime files there:

- `public/<video-name>.<ext>`
- `public/<video-name>.json`

## Configure Whisper.cpp

Captioning installs Whisper.cpp into `whisper.cpp/` and uses model `medium.es` by default.
You can override this without editing code:

```console
WHISPER_MODEL=tiny WHISPER_LANG=es bun run create-subtitles ./examples/winner01.mp4
```

### Non-English languages

For non-English languages, use a model without `.en` suffix and set `WHISPER_LANG`.

## Docs

Get started with Remotion by reading the [fundamentals page](https://www.remotion.dev/docs/the-fundamentals).

## Help

We provide help on our [Discord server](https://remotion.dev/discord).

## Issues

Found an issue with Remotion? [File an issue here](https://github.com/remotion-dev/remotion/issues/new).

## License

Note that for some entities a company license is needed. [Read the terms here](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md).
