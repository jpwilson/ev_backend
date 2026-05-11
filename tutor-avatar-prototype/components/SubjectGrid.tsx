"use client";

import { SUBJECTS, type Subject } from "@/lib/subjects";
import clsx from "clsx";

type Props = {
  selectedId: string | null;
  onSelect: (s: Subject) => void;
  disabled?: boolean;
};

export default function SubjectGrid({ selectedId, onSelect, disabled }: Props) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-5 gap-3">
      {SUBJECTS.map((s) => {
        const active = s.id === selectedId;
        return (
          <button
            key={s.id}
            disabled={disabled}
            onClick={() => onSelect(s)}
            className={clsx(
              "rounded-xl px-3 py-3 text-left border transition",
              "bg-panel border-white/10 hover:border-accent hover:bg-white/5",
              active && "border-accent2 bg-accent/10",
              disabled && "opacity-50 cursor-not-allowed"
            )}
          >
            <div className="text-xl">{s.emoji}</div>
            <div className="text-sm font-medium">{s.name}</div>
            <div className="text-[11px] text-white/50 line-clamp-1">
              {s.blurb}
            </div>
          </button>
        );
      })}
    </div>
  );
}
