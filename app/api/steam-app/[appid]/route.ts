import { NextResponse } from "next/server";

type RouteContext = {
  params: Promise<{
    appid: string;
  }>;
};

function decodeHtml(value: string): string {
  return value
    .replaceAll("&amp;", "&")
    .replaceAll("&quot;", '"')
    .replaceAll("&#039;", "'")
    .replaceAll("&#39;", "'")
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replace(/\s+/g, " ")
    .trim();
}

function firstMatch(text: string, patterns: RegExp[]): string | null {
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match?.[1]) return decodeHtml(match[1]);
  }
  return null;
}

async function fetchAppDetails(appid: string) {
  const url = new URL("https://store.steampowered.com/api/appdetails");
  url.searchParams.set("appids", appid);
  url.searchParams.set("cc", "cn");
  url.searchParams.set("l", "schinese");
  url.searchParams.set("filters", "basic");

  const response = await fetch(url, {
    headers: {
      "User-Agent": "XMODhub-AI-Evaluation/1.0",
    },
  });
  if (!response.ok) return null;

  const payload = await response.json() as Record<string, {
    success?: boolean;
    data?: {
      name?: string;
      header_image?: string;
      release_date?: {
        date?: string;
      };
    };
  }>;
  const data = payload[appid]?.data;
  if (!payload[appid]?.success || !data?.name) return null;

  return {
    appid: Number(appid),
    name: data.name,
    nameZh: data.name,
    cover: data.header_image || `https://cdn.cloudflare.steamstatic.com/steam/apps/${appid}/header.jpg`,
    releaseDate: data.release_date?.date || "-",
  };
}

async function fetchStorePageMetadata(appid: string) {
  const url = new URL(`https://store.steampowered.com/app/${appid}/`);
  url.searchParams.set("cc", "cn");
  url.searchParams.set("l", "schinese");

  const response = await fetch(url, {
    headers: {
      "User-Agent": "XMODhub-AI-Evaluation/1.0",
      Cookie: "birthtime=568022401; lastagecheckage=1-January-1988; wants_mature_content=1",
    },
  });
  if (!response.ok) return null;

  const text = await response.text();
  let name = firstMatch(text, [
    /<div[^>]+class="[^"]*apphub_AppName[^"]*"[^>]*>(.*?)<\/div>/is,
    /<meta\s+property="og:title"\s+content="([^"]+)"/is,
    /<title>(.*?)<\/title>/is,
  ]);
  if (name?.endsWith(" on Steam")) name = name.slice(0, -" on Steam".length).trim();

  const cover = firstMatch(text, [
    /<meta\s+property="og:image"\s+content="([^"]+)"/is,
    /<img[^>]+class="[^"]*game_header_image_full[^"]*"[^>]+src="([^"]+)"/is,
  ]);
  const releaseDate = firstMatch(text, [
    /<div[^>]+class="[^"]*release_date[^"]*"[^>]*>.*?<div[^>]+class="[^"]*date[^"]*"[^>]*>(.*?)<\/div>/is,
  ]);

  if (!name) return null;
  return {
    appid: Number(appid),
    name,
    nameZh: name,
    cover: cover || `https://cdn.cloudflare.steamstatic.com/steam/apps/${appid}/header.jpg`,
    releaseDate: releaseDate || "-",
  };
}

export async function GET(_request: Request, context: RouteContext) {
  const { appid } = await context.params;
  if (!/^\d+$/.test(appid)) {
    return NextResponse.json({ error: "Invalid appid" }, { status: 400 });
  }

  const details = await fetchAppDetails(appid).catch(() => null);
  if (details) return NextResponse.json(details);

  const metadata = await fetchStorePageMetadata(appid).catch(() => null);
  if (metadata) return NextResponse.json(metadata);

  return NextResponse.json({ error: "Steam app metadata not found" }, { status: 404 });
}
