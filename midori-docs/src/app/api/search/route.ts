import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({
    status: "ok",
    message: "Search index endpoint placeholder",
    timestamp: new Date().toISOString(),
  });
}
