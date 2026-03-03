import os
import requests
import json
from rich.console import Console
from rich.panel import Panel
from dotenv import load_dotenv

load_dotenv()
console = Console()

# Chiave OpenRouter passata tramite file .env
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not OPENROUTER_API_KEY:
    console.print("[bold red]ERRORE: Chiave OPENROUTER_API_KEY mancante nel file .env![/bold red]")
    exit(1)

HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "HTTP-Referer": "https://mirko-tornani-ai-lab.com",
    "X-Title": "Mirko Ouroboros Council",
    "Content-Type": "application/json"
}

def get_available_models():
    """Recupera e filtra i modelli attualmente disponibili su OpenRouter."""
    try:
        response = requests.get("https://openrouter.ai/api/v1/models", headers=HEADERS)
        if response.status_code == 200:
            models_data = response.json().get('data', [])
            # Filtriamo modelli troppo esotici o non adatti a compiti complessi per semplificare il lavoro dell'Orchestratore
            whitelist_providers = ['google', 'anthropic', 'openai', 'meta-llama', 'mistralai', 'x-ai']
            filtered_models = []
            
            for m in models_data:
                mid = m['id']
                if any(mid.startswith(p) for p in whitelist_providers) and "vision" not in mid:
                    filtered_models.append({
                        "id": mid,
                        "name": m.get('name', ''),
                        "context_length": m.get('context_length', 0),
                        "pricing": m.get('pricing', {})
                    })
            
            # Ordiniamo per contesto decrescente (i più capaci in alto) e prendiamo i top 30
            sorted_models = sorted(filtered_models, key=lambda x: x['context_length'], reverse=True)[:30]
            return sorted_models
        else:
            console.print(f"[red]Errore recupero modelli: {response.status_code}[/red]")
            return []
    except Exception as e:
        console.print(f"[red]Eccezione nel recupero modelli: {e}[/red]")
        return []

def call_openrouter(model, system_prompt, user_message, chat_history=None):
    if chat_history is None:
        chat_history = []
        
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(chat_history)
    messages.append({"role": "user", "content": user_message})
    
    data = {"model": model, "messages": messages, "temperature": 0.5}
    
    res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=HEADERS, data=json.dumps(data))
    
    if res.status_code == 200:
        return res.json()['choices'][0]['message']['content']
    else:
        return f"Error: {res.status_code} - {res.text}"

def orchestrate_council(topic, available_models):
    """
    La Sovra-Architettura: Un modello Orchestratore sceglie chi dovrà lavorare sul task di Mirko.
    Uso un modello stabile, economico e veloce per questa decisione direzionale (es. Haiku o Gemini Flash).
    """
    orchestrator_model = "google/gemini-1.5-flash" 
    # Mappiamo i modelli per il prompt
    model_list_text = "\n".join([f"- ID: {m['id']} (Contesto: {m['context_length']})" for m in available_models])
    
    system_prompt = """Sei l'ARCHITETTO di Mirko Tornani. 
Il tuo UNICO scopo è leggere il task richiesto da Mirko e assegnare i 2 migliori agenti da una lista di modelli OpenRouter attualmente online.
1. L'Analista (Deve essere un modello eccellente nel ragionamento e nei dati crudi).
2. Il Tattico (Deve essere un modello creativo e critico, tipicamente Anthropic o OpenAI top tier).
Rispondi RIGOROSAMENTE con questo formato JSON:
{"analyst_model": "id_modello", "tactician_model": "id_modello"}
Non aggiungere testo extra."""

    user_prompt = f"TASK: {topic}\n\nMODELLI ATTUALMENTE ONLINE (Scegli da qui):\n{model_list_text}"
    
    with console.status("[bold blue]L'Architetto sta valutando i modelli migliori in tempo reale..."):
        decision_raw = call_openrouter(orchestrator_model, system_prompt, user_prompt)
    
    # Pulizia grezza se restituisce Markdown
    clean_json = decision_raw.replace("```json", "").replace("```", "").strip()
    try:
        decision = json.loads(clean_json)
        return decision['analyst_model'], decision['tactician_model']
    except:
        # Fallback in caso di errore dell'Orchestratore
        console.print("[yellow]Errore parser Architetto. Fallback su default.[/yellow]")
        return "google/gemini-1.5-pro", "anthropic/claude-3.5-sonnet"

def run_council():
    console.print(Panel.fit("[bold cyan]Ouroboros AI Council V2 - Meta Orchestration[/bold cyan]\nMan-in-the-loop: Mirko Tornani"))
    
    # 1. Recupero Modelli Live
    with console.status("[white]Interrogazione OpenRouter per i modelli online...[/white]"):
        models = get_available_models()
    console.print(f"[green]✓ Recuperati {len(models)} modelli Tier-1 attualmente attivi.[/green]")
    
    # 2. Input del Direttore
    topic = console.input("\n[bold green]Mirko (Direttore):[/bold green] Su cosa deve lavorare il Council?\n> ")
    if not topic.strip(): return
    
    # 3. L'Architetto sceglie le API
    analyst_id, tactician_id = orchestrate_council(topic, models)
    console.print(f"[bold cyan]L'Architetto ha assemblato il team:[/bold cyan]")
    console.print(f"🕵️  [cyan]Analista:[/cyan] [bold]{analyst_id}[/bold]")
    console.print(f"♟️  [yellow]Tattico:[/yellow]  [bold]{tactician_id}[/bold]\n")
    
    # 4. FASE 1: L'Analista lavora
    sys_analyst = "Sei l'Analista. Analizza i dati associati al topic in modo iper-razionale. Fornisci un report dati conciso (nessuna divagazione)."
    with console.status(f"[cyan]L'Analista ({analyst_id}) sta elaborando..."):
        analyst_report = call_openrouter(analyst_id, sys_analyst, topic)
    console.print(Panel(analyst_report, title="Analista Report", border_style="cyan"))
    
    # 5. FASE 2: Il Tattico critica/espande
    sys_tactician = "Sei il Tattico (L'Avvocato del Diavolo). Leggi il report dell'Analista: smontalo, trova i punti ciechi strategici e trai una conclusione spietata."
    with console.status(f"[yellow]Il Tattico ({tactician_id}) sta analizzando il report..."):
        tactician_prompt = f"Report dell'Analista sul topic '{topic}':\n\n{analyst_report}\n\nTrova i punti deboli di questa analisi e dai il verdetto tattico."
        tactician_report = call_openrouter(tactician_id, sys_tactician, tactician_prompt)
    console.print(Panel(tactician_report, title="Verdetto del Tattico", border_style="yellow"))
    
    # 6. MAN IN THE LOOP (TU)
    console.print("\n[bold red]ATTENZIONE RICHIESTA: Azione Direttiva del Man-in-the-Loop[/bold red]")
    action = console.input("[bold]Scegli (A)pprova, (R)ifiuta, oppure scrivi un feedback correttivo per il Tattico:[/bold]\n> ")
    
    if action.lower() == 'a':
        console.print("[bold green]✓ Decisione Approvata dal Direttore. Dati confermati.[/bold green]")
    elif action.lower() == 'r':
        console.print("[bold red]❌ Processo abortito per veto del Direttore.[/bold red]")
    else:
        with console.status(f"[magenta]Subroutine correttiva in corso su {tactician_id}..."):
            correction_prompt = f"Il Direttore (Mirko) ha rifiutato in parte e comanda: '{action}'. Adeguati istantaneamente e rifai le conclusioni."
            final_version = call_openrouter(tactician_id, sys_tactician, correction_prompt, [{"role": "assistant", "content": tactician_report}])
        console.print(Panel(final_version, title="Soluzione Ricalcolata (Direttiva Eseguita)", border_style="magenta"))

if __name__ == "__main__":
    run_council()
