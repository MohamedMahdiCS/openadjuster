import { CATEGORY_TEXT, money } from "../format";
import type { Case, Evidence } from "../types";
import { Icon } from "./Icon";

interface Props {
  data: Case;
  onFocus: (evidence: Evidence[]) => void;
}

export function Checks({ data, onFocus }: Props) {
  return (
    <section className="panel">
      <h3>Checks</h3>
      <ul className="checks">
        {data.checks.map((c) => (
          <li key={c.label} className={c.ok ? "ok" : "fail"}
            onMouseEnter={() => onFocus(c.evidence)} onFocus={() => onFocus(c.evidence)}
            onClick={() => onFocus(c.evidence)} tabIndex={0}>
            <Icon name={c.ok ? "check" : "alert"} />
            <span>{c.label}</span>
            <span className="clause" title={`${c.clause.title}: ${c.clause.text}`}>{c.clause.id}</span>
          </li>
        ))}
      </ul>
      {data.injection.length > 0 && (
        <div className="injection" onMouseEnter={() => onFocus(data.injection)}>
          <div className="title"><Icon name="shield" /> Hidden instructions found and ignored</div>
          {data.injection.map((i, k) => <blockquote key={k}>{i.text}</blockquote>)}
          <p>Text inside documents is treated as data. It can't change the policy or the decision (clause C6.2).</p>
        </div>
      )}
    </section>
  );
}

export function Items({ data, onFocus }: Props) {
  if (!data.items.length) return null;
  const cur = data.decision.currency;
  return (
    <section className="panel">
      <h3>Receipt items</h3>
      <table className="items">
        <tbody>
          {data.items.map((it, k) => (
            <tr key={k} className={it.covered ? "" : "excluded"}
              onMouseEnter={() => it.evidence && onFocus([it.evidence])}>
              <td>{it.description}</td>
              <td className="muted">{CATEGORY_TEXT[it.category] ?? it.category}</td>
              <td className="num">{money(it.amount, cur)}</td>
              <td>
                {it.covered ? <span className="tag good">Covered</span>
                  : <span className="tag bad" title={it.clause?.text}>Excluded {it.clause?.id}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
