interface LanguageSelectorProps {
  currentLang: string;
  onSelectLang: (lang: string) => void;
}

export default function LanguageSelector({ currentLang, onSelectLang }: LanguageSelectorProps) {
  return (
    <div className="language-selector-wrapper">
      <select
        value={currentLang}
        onChange={(e) => onSelectLang(e.target.value)}
        aria-label="Select language"
        className="language-dropdown-pill"
      >
        <option value="EN">ENGLISH GUIDE</option>
        <option value="ZH">中文指南</option>
      </select>
    </div>
  );
}
