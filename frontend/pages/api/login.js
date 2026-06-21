import crypto from "crypto";

const SECRET = process.env.SESSION_SECRET || "dev-secret-change-me";

function sign(value) {
  const h = crypto.createHmac("sha256", SECRET).update(value).digest("hex");
  return `${value}.${h}`;
}

export default function handler(req, res) {
  if (req.method !== "POST") {
    res.status(405).json({ error: "Method not allowed" });
    return;
  }

  const { password } = req.body || {};
  const correctPassword = process.env.APP_PASSWORD;

  if (!correctPassword) {
    res.status(500).json({ error: "Server not configured: APP_PASSWORD missing" });
    return;
  }

  if (password !== correctPassword) {
    res.status(401).json({ error: "Incorrect password" });
    return;
  }

  const token = sign("authenticated");
  res.setHeader(
    "Set-Cookie",
    `session=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${60 * 60 * 24 * 7}`
  );
  res.status(200).json({ ok: true });
}
