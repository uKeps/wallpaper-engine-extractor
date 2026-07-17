# Wallpaper Engine PKG Extractor

Extrai a imagem (ou vídeo) de dentro dos wallpapers baixados pelo Wallpaper Engine, sem precisar instalar nada além do Python.

Quando você se inscreve num wallpaper na Steam Workshop, os arquivos baixados vêm num formato proprietário (`scene.pkg`, com texturas `.tex` lá dentro) ou, no caso de wallpapers de vídeo, já vêm como `.mp4`/`.webm` puro. Esse script lê o `scene.pkg`, decodifica as texturas `.tex` e salva tudo como PNG/JPG/BMP normal. Vídeos são só copiados como estão.

## Features

- Não precisa de nenhuma dependência para a maioria dos casos (texturas PNG/JPG funcionam direto)
- Interface gráfica (roda `main.py` sem argumentos) e também funciona via linha de comando
- Detecta automaticamente os wallpapers instalados via Steam, com miniatura de preview, sem precisar caçar pasta
- Arrastar e soltar arquivos na janela da GUI
- Extrai vídeos (`.mp4`/`.webm`) copiando direto
- Funciona com qualquer versão do formato `.tex` — não usa offset fixo, detecta o layout dinamicamente
- Modo "só imagens": apaga shaders, scripts e JSON, deixando só o wallpaper
- Pillow (opcional) para converter texturas RAW/RLE em PNG e gerar as miniaturas de preview
- tkinterdnd2 (opcional) para habilitar o drag & drop na GUI

## Instalação

Precisa de [Python 3.6+](https://www.python.org/downloads/) (marcar "Add Python to PATH" na instalação).

```bash
git clone https://github.com/uKeps/wallpaper-pkg-extractor.git
cd wallpaper-pkg-extractor
pip install -r requirements.txt
```

O `pip install` é opcional — sem ele, PNG e JPG extraem normalmente, só texturas RAW/RLE (mais raras) saem como BMP em vez de PNG.

## Onde ficam os arquivos

A Steam guarda os wallpapers baixados aqui:

```
C:\Program Files (x86)\Steam\steamapps\workshop\content\431960\<ID_do_wallpaper>\
```

Dentro de cada pasta:

| Arquivo | O que é |
|---|---|
| `scene.pkg` | O pacote com os assets do wallpaper |
| `preview.jpg` | Miniatura de preview |
| `project.json` | Metadados do wallpaper |

Mas na prática não precisa nem procurar isso manualmente — o botão de detecção automática da GUI (ou `--list-wallpapers` no CLI) já lista tudo pra você.

## Uso

### GUI

```bash
python main.py
```

1. Clique em **Browse** e selecione o `scene.pkg`, `.tex` ou o vídeo — ou arraste o arquivo pra janela, ou clique em **Detect Installed Wallpapers (Steam)** pra escolher de uma lista com preview
2. Confira a pasta de saída (já vem preenchida do lado do arquivo de entrada)
3. Deixe marcado **"Keep ONLY wallpaper images"** se quiser só a imagem, sem os arquivos extras (só afeta wallpapers do tipo scene)
4. Clique em **Extract & Convert Assets**

Wallpapers do tipo "web" aparecem na lista de detecção mas não dá pra extrair — eles não têm um asset fixo pra extrair.

### CLI

```bash
# extração básica — sai em scene_extracted/ do lado do .pkg
python main.py "caminho/scene.pkg"

# pasta de saída customizada
python main.py "caminho/scene.pkg" -o "C:/Users/SeuUsuario/Desktop/saida"

# extrair um .tex avulso
python main.py "caminho/textura.tex" -o "C:/Users/SeuUsuario/Desktop/saida"

# manter todos os arquivos (não apagar shaders, JSON etc)
python main.py "caminho/scene.pkg" --no-cleanup

# extrair também os mipmaps menores, não só a resolução máxima
python main.py "caminho/scene.pkg" --all-mipmaps

# copiar um wallpaper de vídeo
python main.py "caminho/video.mp4" -o "C:/Users/SeuUsuario/Desktop/saida"

# forçar abrir a GUI mesmo passando argumentos
python main.py --gui

# listar os wallpapers instalados (título, ID, tipo, caminho do asset)
python main.py --list-wallpapers
```

Referência completa:

```
positional arguments:
  input                 Caminho do scene.pkg, de um .tex avulso, ou de um vídeo (.mp4/.webm)

options:
  -h, --help            Mostra a ajuda e sai
  -o, --output PATH     Pasta de saída (padrão: <nome>_extracted do lado do input)
  --no-tex-convert      Não converte os .tex extraídos pra PNG/JPG
  --all-mipmaps         Extrai todos os níveis de mipmap, não só o de maior resolução
  --no-cleanup          Mantém todos os arquivos extraídos (shaders, JSON, scripts etc)
  --gui                 Força abrir a GUI mesmo passando argumentos
  --list-wallpapers     Lista os wallpapers instalados via Steam Workshop e sai
```

## Estrutura do projeto

```
wallpaper-pkg-extractor/
├── main.py               # ponto de entrada — decide entre GUI ou CLI
├── requirements.txt      # dependências opcionais (Pillow, tkinterdnd2)
├── LICENSE
├── README.md
└── src/
    ├── extractor.py          # parser do .pkg
    ├── tex_parser.py         # decoder do .tex e conversão de imagem
    ├── steam_finder.py       # varredura das bibliotecas Steam/Workshop
    ├── wallpaper_browser.py  # janela da GUI que lista os wallpapers detectados
    ├── video_extractor.py    # copia wallpapers de vídeo
    └── gui.py                # GUI em Tkinter
```

## Como funciona por baixo dos panos

**Formato `.pkg`**: é um arquivo binário simples — string com o caminho raiz (tipo `PKGV0024`, identifica a versão do Wallpaper Engine), um uint32 com a quantidade de arquivos, depois as entradas (nome, offset, tamanho) e por fim os dados de todos os arquivos concatenados.

**Formato `.tex`**: container de textura com três seções — `TEXV` (versão), `TEXI` (largura/altura) e `TEXB` (dados binários dos mipmaps). Cada mipmap guarda largura, altura, tamanho, e os bytes da imagem, que podem ser PNG cru, JPG cru, ou BGRA comprimido em RLE. Em vez de usar offsets fixos (que quebram entre versões), o script procura o padrão de bytes `(largura, altura)` logo depois do marcador `TEXB` pra achar o primeiro mipmap — por isso funciona em qualquer versão do formato.

**Vídeos**: não usam `.pkg` nenhum, o arquivo `.mp4`/`.webm` já fica solto na pasta do Workshop. "Extrair" aqui é só copiar pro destino escolhido.

## Aviso

Isso é pra uso pessoal — tipo recuperar a imagem de um wallpaper que você já tem. Respeite os direitos autorais de quem criou o wallpaper e não redistribua os assets extraídos sem permissão.

## Licença

[MIT](LICENSE) © uKeps
