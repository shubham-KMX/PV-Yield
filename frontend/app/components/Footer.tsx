/**
 * Site footer: brand blurb, quick links, data-source credits, legal note.
 */
export default function Footer() {
  return (
    <footer className="mt-auto bg-[#241812] px-6 pb-8 pt-12 text-[#e8d5c5]">
      <div className="mx-auto max-w-[1120px]">
        <div className="grid gap-8 md:grid-cols-[2fr_1fr_1fr]">
          {/* brand + blurb */}
          <div>
            <div className="mb-3 flex items-center gap-2.5 text-lg font-extrabold">
              <span className="h-[22px] w-[22px] rounded-full bg-[radial-gradient(circle_at_40%_35%,#fffdf5,#ffc457_55%,#ff9d3c_100%)]" />
              PV-<span className="text-sunset-gradient">Yield</span>
            </div>
            <p className="max-w-[320px] text-sm leading-relaxed text-[#b89a85]">
              Honest rooftop solar estimates for Indian homes — built on
              measured roof area, real satellite weather, and industry-standard
              solar physics.
            </p>
          </div>

          {/* product links */}
          <div>
            <h5 className="mb-3.5 text-xs font-semibold uppercase tracking-wider text-[#f0a97e]">
              Product
            </h5>
            {["Analyze my roof", "How it works", "Methodology"].map((t) => (
              <a
                key={t}
                href="#"
                className="mb-2 block text-sm text-[#c9b3a4] transition-colors hover:text-white"
              >
                {t}
              </a>
            ))}
          </div>

          {/* data sources */}
          <div>
            <h5 className="mb-3.5 text-xs font-semibold uppercase tracking-wider text-[#f0a97e]">
              Data sources
            </h5>
            {["Google Maps", "NASA POWER", "NREL PVWatts"].map((t) => (
              <a
                key={t}
                href="#"
                className="mb-2 block text-sm text-[#c9b3a4] transition-colors hover:text-white"
              >
                {t}
              </a>
            ))}
          </div>
        </div>

        <div className="mt-8 flex justify-between border-t border-[#3a281e] pt-5 text-xs text-[#9c7a63]">
          <span>© 2026 PV-Yield</span>
          <span>Estimates only — confirm with a certified installer.</span>
        </div>
      </div>
    </footer>
  );
}
