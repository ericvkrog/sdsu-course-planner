export default function ConflictAlert({ conflicts, onDismiss }) {
  if (!conflicts || conflicts.length === 0) return null;

  // Errors = academically invalid (prereq order, offering, standing).
  // Warnings = soft, user-chosen (e.g. a semester above the unit target).
  const errors = conflicts.filter((c) => c.severity !== "warning");
  const warnings = conflicts.filter((c) => c.severity === "warning");

  return (
    <div className="space-y-3 mb-4">
      {errors.length > 0 && (
        <Banner
          tone="red"
          title={`${errors.length} scheduling conflict${errors.length !== 1 ? "s" : ""}`}
          items={errors}
          onDismiss={onDismiss}
        />
      )}
      {warnings.length > 0 && (
        <Banner
          tone="amber"
          title={`${warnings.length} heads-up${warnings.length !== 1 ? "s" : ""} (not blocking)`}
          items={warnings}
          onDismiss={onDismiss}
        />
      )}
    </div>
  );
}

const TONES = {
  red: {
    box: "bg-red-50 border-red-200",
    title: "text-red-800",
    text: "text-red-700",
    btn: "text-red-400 hover:text-red-600",
  },
  amber: {
    box: "bg-amber-50 border-amber-200",
    title: "text-amber-800",
    text: "text-amber-700",
    btn: "text-amber-400 hover:text-amber-600",
  },
};

function Banner({ tone, title, items, onDismiss }) {
  const t = TONES[tone];
  return (
    <div className={`${t.box} border rounded-lg p-4`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <h3 className={`text-sm font-semibold ${t.title} mb-1`}>{title}</h3>
          <ul className="space-y-1">
            {items.map((c, i) => (
              <li key={i} className={`text-sm ${t.text}`}>
                {c.course_code !== "*" && (
                  <span className="font-mono font-medium">{c.course_code} — </span>
                )}
                {c.reason}
              </li>
            ))}
          </ul>
        </div>
        {onDismiss && (
          <button
            onClick={onDismiss}
            className={`${t.btn} text-lg leading-none mt-0.5`}
            aria-label="Dismiss"
          >
            ×
          </button>
        )}
      </div>
    </div>
  );
}
