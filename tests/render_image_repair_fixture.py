"""Render a synthetic Basic replacement/recovery; never connect to the real Anki."""
import argparse
import base64
import html
import json
from pathlib import Path

from test_image_repair import ImageRepairTests, ImageState
from modules.anki_connector import AnkiConnector


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    case = ImageRepairTests()
    case.setUp()
    try:
        case.state = ImageState(basic=True)
        case.client = AnkiConnector(session=case.state)
        case.request["field"] = "Back"
        preview = case.prepare()
        after = case.run_request()
        case.request = {**preview["recovery"], "confirmed": False}
        case.prepare()
        restored = case.run_request()
        frames = []
        for title, rendered in (("Antes", preview["rendered_before"]), ("Depois", after["rendered_after"]),
                                ("Restaurada", restored["rendered_after"])):
            for side, body in rendered["21"].items():
                for filename, data in case.state.media.items():
                    if filename.endswith((".png", ".jpg")):
                        mime = "image/png" if filename.endswith(".png") else "image/jpeg"
                        body = body.replace(f'src="{filename}"', f'src="data:{mime};base64,{base64.b64encode(data).decode()}"')
                frames.append(f'<section><h2>{html.escape(title)} · {"Frente" if side == "question" else "Verso"}</h2><div class="card">{body}</div></section>')
        page = ('<!doctype html><meta charset="utf-8"><title>Fixture local de reparo de imagem</title>'
                '<style>body{font:16px Arial;background:#eee;margin:24px}main{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}'
                'section{background:white;padding:18px}section:nth-child(2){grid-column:1;grid-row:2}section:nth-child(3){grid-column:2;grid-row:1}'
                'section:nth-child(4){grid-column:2;grid-row:2}section:nth-child(5){grid-column:3;grid-row:1}section:nth-child(6){grid-column:3;grid-row:2}'
                '.card{text-align:center}.card img{display:block;max-width:100%;max-height:350px;margin:12px auto}h2{font-size:16px}</style>'
                '<h1>Fixture sintética: troca e restauração</h1><p>HTML devolvido pelo transporte AnkiConnect simulado. Nenhum dado pessoal acessado.</p><main>'
                + ''.join(frames) + '</main>')
        (args.output / "fixture.html").write_text(page)
        (args.output / "receipt.json").write_text(json.dumps({"preview": preview, "after": after, "restored": restored}, ensure_ascii=False, indent=2))
        print(args.output / "fixture.html")
    finally:
        case.doCleanups()


if __name__ == "__main__":
    main()
