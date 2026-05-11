"use client";

import clsx from "clsx";

export type Provider = "simli" | "hedra";

type Props = {
  value: Provider;
  onChange: (p: Provider) => void;
  disabled?: boolean;
};

export default function ProviderToggle({ value, onChange, disabled }: Props) {
  return (
    <div className="inline-flex rounded-full bg-panel border border-white/10 p-1">
      {(["simli", "hedra"] as Provider[]).map((p) => (
        <button
          key={p}
          disabled={disabled}
          onClick={() => onChange(p)}
          className={clsx(
            "px-4 py-1.5 text-sm rounded-full transition",
            value === p
              ? "bg-accent text-white"
              : "text-white/70 hover:text-white",
            disabled && "opacity-50 cursor-not-allowed"
          )}
        >
          {p === "simli" ? "Simli (2D)" : "Hedra (3D)"}
        </button>
      ))}
    </div>
  );
}
