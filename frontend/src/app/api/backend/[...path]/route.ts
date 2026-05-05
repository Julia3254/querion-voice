import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{
    path: string[];
  }>;
};

function cleanBaseUrl(url: string) {
  return url.trim().replace(/\/$/, "");
}

function getBackendBaseUrl() {
  const backendUrl = process.env.BACKEND_URL;

  if (backendUrl && backendUrl.trim()) {
    return cleanBaseUrl(backendUrl);
  }

  const publicApiUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

  if (
    publicApiUrl &&
    publicApiUrl.trim() &&
    publicApiUrl.startsWith("http")
  ) {
    return cleanBaseUrl(publicApiUrl);
  }

  return "http://127.0.0.1:8000";
}

async function proxyToBackend(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;

  const backendBaseUrl = getBackendBaseUrl();
  const backendPath = path.join("/");
  const targetUrl = `${backendBaseUrl}/${backendPath}${request.nextUrl.search}`;

  const headers = new Headers(request.headers);

  headers.delete("host");
  headers.delete("content-length");

  const init: RequestInit = {
    method: request.method,
    headers,
    cache: "no-store",
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.arrayBuffer();
  }

  try {
    const response = await fetch(targetUrl, init);

    const responseHeaders = new Headers(response.headers);
    responseHeaders.delete("content-encoding");
    responseHeaders.delete("content-length");

    return new NextResponse(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (error) {
    console.error("Backend proxy error:", error);

    return NextResponse.json(
      {
        error: "Nie udało się połączyć z backendem.",
        targetUrl,
      },
      {
        status: 502,
      }
    );
  }
}

export async function GET(request: NextRequest, context: RouteContext) {
  return proxyToBackend(request, context);
}

export async function POST(request: NextRequest, context: RouteContext) {
  return proxyToBackend(request, context);
}

export async function PUT(request: NextRequest, context: RouteContext) {
  return proxyToBackend(request, context);
}

export async function PATCH(request: NextRequest, context: RouteContext) {
  return proxyToBackend(request, context);
}

export async function DELETE(request: NextRequest, context: RouteContext) {
  return proxyToBackend(request, context);
}

export async function OPTIONS() {
  return new NextResponse(null, {
    status: 204,
  });
}