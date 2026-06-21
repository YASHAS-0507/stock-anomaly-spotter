import { NextResponse } from "next/server";

export const config = {
  matcher: ["/", "/dashboard"],
};

export function middleware(req) {
  const session = req.cookies.get("session");
  if (!session) {
    const loginUrl = new URL("/login", req.url);
    return NextResponse.redirect(loginUrl);
  }
  return NextResponse.next();
}
