import { Link } from "react-router-dom";

const FEATURES = [
  {
    icon: "🎓",
    title: "Every major, mapped",
    body: "All 171 SDSU bachelor's degrees. Pick yours and get a full semester-by-semester path to graduation.",
  },
  {
    icon: "🔗",
    title: "Prerequisites, handled",
    body: "We read the catalog's prereq chains so every course lands after what it depends on — no dead ends, no surprises.",
  },
  {
    icon: "🔁",
    title: "Swap with confidence",
    body: "Click any elective to see the classes you're actually eligible for that term — then swap it in with one tap.",
  },
  {
    icon: "🧮",
    title: "Balanced unit loads",
    body: "Set your pace with the units slider. We pack each semester to your target and flag anything overloaded.",
  },
  {
    icon: "📅",
    title: "GE & grad requirements built in",
    body: "General Education, GWAR, and American Institutions are included automatically — nothing slips through.",
  },
  {
    icon: "🖐️",
    title: "Drag to adjust",
    body: "Move any course between semesters. We re-check prerequisites and standing instantly.",
  },
];

const STEPS = [
  { n: "1", title: "Tell us your major", body: "Choose your degree and list anything you've already finished." },
  { n: "2", title: "Generate your plan", body: "Get a valid, prerequisite-aware schedule in seconds." },
  { n: "3", title: "Make it yours", body: "Drag, swap, and tune unit loads until the plan fits your life." },
];

export default function Landing() {
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Nav */}
      <header className="bg-sdsu-red shadow-sm sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-white rounded-full flex items-center justify-center">
              <span className="text-sdsu-red font-black text-sm">S</span>
            </div>
            <span className="text-white font-bold text-lg tracking-tight">
              SDSU Course Planner
            </span>
          </div>
          <Link
            to="/start"
            className="text-white text-sm font-semibold border border-white/40 rounded-lg px-4 py-1.5 hover:bg-white/10 transition-colors"
          >
            Get Started
          </Link>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden bg-gradient-to-b from-sdsu-red to-red-800">
        <div className="max-w-4xl mx-auto px-6 py-20 sm:py-28 text-center">
          <span className="inline-block bg-white/15 text-white text-xs font-semibold tracking-wide uppercase rounded-full px-3 py-1 mb-6">
            For San Diego State students
          </span>
          <h1 className="text-4xl sm:text-5xl font-black text-white leading-tight tracking-tight">
            Graduate on time,
            <br className="hidden sm:block" /> without the guesswork.
          </h1>
          <p className="mt-5 text-lg text-red-100 max-w-2xl mx-auto">
            Build a complete, prerequisite-aware 4-year plan in seconds. Pick your
            major, and we'll handle the ordering, the unit loads, and every
            graduation requirement.
          </p>
          <div className="mt-9 flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              to="/start"
              className="bg-white text-sdsu-red font-semibold px-7 py-3 rounded-lg shadow-sm hover:bg-red-50 transition-colors"
            >
              Build My Plan →
            </Link>
            <a
              href="#how-it-works"
              className="text-white font-semibold px-7 py-3 rounded-lg border border-white/40 hover:bg-white/10 transition-colors"
            >
              See how it works
            </a>
          </div>
          <p className="mt-6 text-sm text-red-200">
            Free · No account needed · 171 majors supported
          </p>
        </div>
      </section>

      {/* Features */}
      <section className="max-w-6xl mx-auto px-6 py-20 w-full">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold text-gray-900">
            Everything you need to plan your degree
          </h2>
          <p className="mt-3 text-gray-500 max-w-2xl mx-auto">
            Built on SDSU's real course catalog — not a spreadsheet you have to
            keep up to date yourself.
          </p>
        </div>
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <div
              key={f.title}
              className="bg-white rounded-2xl border border-gray-200 p-6 shadow-sm hover:shadow-md transition-shadow"
            >
              <div className="text-3xl mb-3">{f.icon}</div>
              <h3 className="font-semibold text-gray-900 mb-1.5">{f.title}</h3>
              <p className="text-sm text-gray-500 leading-relaxed">{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="bg-white border-y border-gray-200">
        <div className="max-w-5xl mx-auto px-6 py-20 w-full">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-bold text-gray-900">How it works</h2>
            <p className="mt-3 text-gray-500">Three steps to a plan you can trust.</p>
          </div>
          <div className="grid gap-8 sm:grid-cols-3">
            {STEPS.map((s) => (
              <div key={s.n} className="text-center">
                <div className="w-12 h-12 mx-auto bg-sdsu-red text-white rounded-full flex items-center justify-center font-bold text-lg mb-4">
                  {s.n}
                </div>
                <h3 className="font-semibold text-gray-900 mb-1.5">{s.title}</h3>
                <p className="text-sm text-gray-500 leading-relaxed">{s.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="max-w-4xl mx-auto px-6 py-20 w-full text-center">
        <h2 className="text-3xl font-bold text-gray-900">
          Ready to map out your degree?
        </h2>
        <p className="mt-3 text-gray-500">
          It takes about a minute. No sign-up required.
        </p>
        <Link
          to="/start"
          className="inline-block mt-7 bg-sdsu-red text-white font-semibold px-8 py-3 rounded-lg shadow-sm hover:bg-red-700 transition-colors"
        >
          Get Started →
        </Link>
      </section>

      {/* Footer */}
      <footer className="bg-gray-900 text-gray-400 text-sm">
        <div className="max-w-6xl mx-auto px-6 py-8 flex flex-col sm:flex-row items-center justify-between gap-3">
          <span>SDSU Course Planner — an unofficial student tool.</span>
          <span className="text-gray-500">
            Not affiliated with San Diego State University.
          </span>
        </div>
      </footer>
    </div>
  );
}
