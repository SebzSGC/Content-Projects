import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  try {
    const { provider, apiKey } = await req.json();

    if (!apiKey || typeof apiKey !== "string" || !apiKey.trim()) {
      return NextResponse.json(
        { valid: false, error: "Debes proporcionar una clave API válida." },
        { status: 400 }
      );
    }

    const trimmedKey = apiKey.trim();

    if (provider === "gemini") {
      // Test Gemini API via Google Generative Language REST with candidate models
      const candidateModels = [
        "gemini-3.8-flash",
        "gemini-2.5-flash",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
      ];

      let lastError = "";
      let workingModel = "";

      for (const model of candidateModels) {
        const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${trimmedKey}`;
        const res = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            contents: [{ parts: [{ text: "Responde únicamente con la palabra OK." }] }],
          }),
        });

        if (res.ok) {
          workingModel = model;
          break;
        } else {
          const errorData = await res.json().catch(() => ({}));
          lastError =
            errorData?.error?.message ||
            `Error HTTP ${res.status}: Clave de Google Gemini no admitida por ${model}.`;
        }
      }

      if (!workingModel) {
        return NextResponse.json({ valid: false, error: lastError }, { status: 400 });
      }

      return NextResponse.json({
        valid: true,
        provider: "gemini",
        model: workingModel,
        message: `Conexión exitosa con Google Gemini (${workingModel}).`,
      });
    }

    if (provider === "groq") {
      // Test Groq API
      const res = await fetch("https://api.groq.com/openai/v1/models", {
        headers: {
          Authorization: `Bearer ${trimmedKey}`,
        },
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        const msg =
          errorData?.error?.message ||
          `Error HTTP ${res.status}: Clave de Groq inválida.`;
        return NextResponse.json({ valid: false, error: msg }, { status: 400 });
      }

      return NextResponse.json({
        valid: true,
        provider: "groq",
        model: "llama-3.3-70b-versatile",
        message: "Conexión exitosa con Groq Cloud (Llama 3.3 70B & Whisper).",
      });
    }

    if (provider === "openai") {
      // Test OpenAI API
      const res = await fetch("https://api.openai.com/v1/models", {
        headers: {
          Authorization: `Bearer ${trimmedKey}`,
        },
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        const msg =
          errorData?.error?.message ||
          `Error HTTP ${res.status}: Clave de OpenAI inválida.`;
        return NextResponse.json({ valid: false, error: msg }, { status: 400 });
      }

      return NextResponse.json({
        valid: true,
        provider: "openai",
        model: "gpt-4o-mini",
        message: "Conexión exitosa con OpenAI (GPT-4o & Whisper-1).",
      });
    }

    return NextResponse.json(
      { valid: false, error: `Proveedor no soportado: ${provider}` },
      { status: 400 }
    );
  } catch (err: any) {
    return NextResponse.json(
      { valid: false, error: err?.message || "Error interno al verificar la clave API." },
      { status: 500 }
    );
  }
}
