import { NextResponse } from "next/server";

function backendBaseUrl(request: Request) {
  if (process.env.NEXT_PUBLIC_API_BASE_URL) return process.env.NEXT_PUBLIC_API_BASE_URL;

  const url = new URL(request.url);
  return `${url.protocol}//${url.hostname}:8000`;
}

export async function POST(request: Request) {
  const backendUrl = `${backendBaseUrl(request)}/sessions/tv`;

  try {
    const response = await fetch(backendUrl, {
      method: "POST",
      cache: "no-store",
    });

    const body = await response.text();

    if (!response.ok) {
      return new NextResponse(body || "Nie udało się utworzyć sesji TV.", {
        status: response.status,
      });
    }

    return new NextResponse(body, {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: "Nie udało się połączyć z backendem.",
        backendUrl,
      },
      { status: 502 }
    );
  }
}
