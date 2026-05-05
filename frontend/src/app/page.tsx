import Link from "next/link";

export default function HomePage() {
  return (
    <main
      style={{
        minHeight: "100vh",
        background: "#ffffff",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
        fontFamily: "Arial, sans-serif",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 16, alignItems: "center" }}>
        <h1 style={{ margin: 0, fontSize: 28 }}>Voice Avatar V2</h1>
        <Link href="/phone" style={linkStyle}>Telefon</Link>
        <Link href="/tv" style={linkStyle}>Telewizor</Link>
      </div>
    </main>
  );
}

const linkStyle = {
  minWidth: 260,
  textAlign: "center" as const,
  padding: "16px 22px",
  borderRadius: 16,
  background: "#2d6a4f",
  color: "#ffffff",
  textDecoration: "none",
  fontWeight: 700,
};
