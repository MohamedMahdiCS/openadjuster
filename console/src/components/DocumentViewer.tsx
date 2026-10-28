import { fileUrl } from "../api";
import type { Case, Evidence } from "../types";

interface Props {
  data: Case;
  activeDoc: string;
  onSelect: (docId: string) => void;
  highlights: Evidence[];
}

export function DocumentViewer({ data, activeDoc, onSelect, highlights }: Props) {
  const doc = data.documents.find((d) => d.doc_id === activeDoc) ?? data.documents[0];
  if (!doc) return <div className="panel empty">No documents in this claim.</div>;
  const strong = highlights.filter((h) => h.doc_id === doc.doc_id);
  const injected = data.injection.filter((i) => i.doc_id === doc.doc_id);
  const stroke = Math.max(2, doc.width / 400);

  return (
    <div className="panel viewer">
      <div className="tabs" role="tablist">
        {data.documents.map((d) => {
          const hot = highlights.some((h) => h.doc_id === d.doc_id);
          return (
            <button key={d.doc_id} role="tab" aria-selected={d.doc_id === doc.doc_id}
              className={`tab ${d.doc_id === doc.doc_id ? "on" : ""} ${hot ? "hot" : ""}`}
              onClick={() => onSelect(d.doc_id)}>
              {d.label}
            </button>
          );
        })}
      </div>
      <div className="page">
        <img src={fileUrl(data.packet_id, doc.file)} alt={doc.label} />
        <svg className="overlay" viewBox={`0 0 ${doc.width} ${doc.height}`}
          preserveAspectRatio="none" aria-hidden="true">
          {doc.fields.filter((f) => f.box).map((f) => {
            const [x, y, w, h] = f.box!;
            return (
              <rect key={f.name} className="field" x={x} y={y} width={w} height={h}
                strokeWidth={stroke}>
                <title>{`${f.name.replaceAll("_", " ")}: ${f.value}`}</title>
              </rect>
            );
          })}
          {injected.map((i, k) => {
            const [x, y, w, h] = i.box;
            return <rect key={`inj${k}`} className="injected" x={x - 4} y={y - 4}
              width={w + 8} height={h + 8} strokeWidth={stroke * 1.5} />;
          })}
          {strong.map((e, k) => {
            const [x, y, w, h] = e.box;
            return <rect key={`hl${k}`} className="highlight" x={x - 4} y={y - 4}
              width={w + 8} height={h + 8} strokeWidth={stroke * 1.5} />;
          })}
        </svg>
      </div>
      <p className="hint">Boxes show where each value was read. Hover a check or an item to see its evidence.</p>
    </div>
  );
}
