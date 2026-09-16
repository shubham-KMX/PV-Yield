/**
 * "How it works" — four steps from address to answer.
 */
import { MapPin, Ruler, Sun, IndianRupee } from "lucide-react";

const STEPS = [
  {
    icon: MapPin,
    title: "1. Locate",
    text: "We pull a satellite image of your exact rooftop.",
  },
  {
    icon: Ruler,
    title: "2. Measure",
    text: "AI outlines your roof and measures its real area.",
  },
  {
    icon: Sun,
    title: "3. Simulate",
    text: "A full year of hourly sun is run through solar physics.",
  },
  {
    icon: IndianRupee,
    title: "4. Report",
    text: "You get generation, savings, subsidy and payback.",
  },
];

export default function HowItWorks() {
  return (
    <section
      id="how"
      className="border-y border-sunset-line bg-gradient-to-b from-[#fff8f0] to-[#fdfbf9] px-6 py-16"
    >
      <div className="mx-auto max-w-[1120px]">
        <div className="text-center text-[13px] font-extrabold uppercase tracking-[0.12em] text-sunset-orange">
          How it works
        </div>
        <h2 className="mt-2 text-center text-3xl font-extrabold tracking-tight">
          From address to answer in four steps
        </h2>

        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map(({ icon: Icon, title, text }) => (
            <div
              key={title}
              className="rounded-[18px] border border-sunset-line bg-white p-[22px] text-center shadow-[0_4px_16px_rgba(180,120,80,0.06)] transition-transform hover:-translate-y-1"
            >
              <div className="mx-auto mb-3.5 grid h-[46px] w-[46px] place-items-center rounded-xl bg-gradient-to-br from-[rgba(255,196,87,0.25)] to-[rgba(249,115,22,0.15)]">
                <Icon className="h-[22px] w-[22px] text-sunset-orange" />
              </div>
              <h4 className="text-[15px] font-bold">{title}</h4>
              <p className="mt-1.5 text-[13px] leading-relaxed text-sunset-muted">
                {text}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
