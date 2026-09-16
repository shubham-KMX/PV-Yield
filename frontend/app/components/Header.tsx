/**
 * Top navigation bar. Sticky, translucent, with the glowing sun brand mark.
 */
export default function Header() {
  return (
    <header className="sticky top-0 z-20 border-b border-sunset-line bg-[rgba(253,251,249,0.8)] backdrop-blur-md">
      <div className="mx-auto flex h-[66px] max-w-[1120px] items-center justify-between px-6">
        {/* brand */}
        <div className="flex items-center gap-2.5 text-[19px] font-extrabold">
          <span className="sun-orb h-6 w-6" />
          PV-<span className="text-sunset-gradient">Yield</span>
        </div>

        {/* links */}
        <nav className="hidden gap-7 text-sm font-semibold text-sunset-muted md:flex">
          <a href="#how" className="transition-colors hover:text-sunset-orange">
            How it works
          </a>
          <a href="#results" className="transition-colors hover:text-sunset-orange">
            Example
          </a>
          <a href="#method" className="transition-colors hover:text-sunset-orange">
            Methodology
          </a>
        </nav>

        {/* cta */}
        <a
          href="#analyze"
          className="rounded-[10px] bg-gradient-to-br from-sunset-orange-lt to-sunset-orange px-[18px] py-[9px] text-sm font-bold text-white shadow-[0_4px_14px_rgba(249,115,22,0.35)] transition-transform hover:scale-[1.03]"
        >
          Analyze my roof
        </a>
      </div>
    </header>
  );
}
