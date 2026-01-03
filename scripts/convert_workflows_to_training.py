#!/usr/bin/env python3
"""
n8n Workflow to LoRA Training Data Converter

Konverterar n8n workflow JSON-filer till JSONL training data för LoRA fine-tuning.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Any
import re


class WorkflowToTrainingConverter:
    def __init__(self, workflow_dir: str, output_file: str):
        self.workflow_dir = Path(workflow_dir)
        self.output_file = Path(output_file)
        self.training_examples = []
        self.processed_count = 0
        self.error_count = 0

    def extract_node_summary(self, node: Dict[str, Any]) -> str:
        """Extraherar en beskrivning av vad en nod gör."""
        node_type = node.get('type', 'unknown')
        node_name = node.get('name', 'unnamed')
        parameters = node.get('parameters', {})

        # Extrahera operation om det finns
        operation = parameters.get('operation', '')
        resource = parameters.get('resource', '')

        if operation and resource:
            return f"{node_name} ({node_type}): {operation} on {resource}"
        elif operation:
            return f"{node_name} ({node_type}): {operation}"
        else:
            return f"{node_name} ({node_type})"

    def extract_ai_prompts(self, node: Dict[str, Any]) -> List[str]:
        """Extraherar AI prompts från noder."""
        prompts = []
        parameters = node.get('parameters', {})

        # Kolla efter system prompts i olika format
        if 'jsonBody' in parameters:
            json_body_str = parameters['jsonBody']
            # Försök extrahera system prompt från JSON-sträng
            try:
                # Enkel regex för att hitta system content
                system_match = re.search(r'"role":\s*"system".*?"content":\s*"([^"]+)"', json_body_str, re.DOTALL)
                if system_match:
                    prompts.append(system_match.group(1))
            except:
                pass

        # Kolla efter prompts i jsCode
        if 'jsCode' in parameters:
            prompts.append(f"JavaScript Code: {parameters['jsCode'][:200]}...")

        # Kolla efter systemMessage i langchain noder
        if 'systemMessage' in parameters:
            prompts.append(parameters['systemMessage'])

        return prompts

    def extract_workflow_logic(self, workflow_data: Dict[str, Any]) -> str:
        """Skapar en beskrivning av workflow-logiken."""
        nodes = workflow_data.get('nodes', [])
        connections = workflow_data.get('connections', {})

        logic_parts = []

        # Summera noder
        node_types = {}
        for node in nodes:
            node_type = node.get('type', 'unknown').split('.')[-1]
            node_types[node_type] = node_types.get(node_type, 0) + 1

        logic_parts.append("Workflow består av:")
        for node_type, count in sorted(node_types.items()):
            logic_parts.append(f"- {count}x {node_type}")

        # Extrahera dataflöde
        logic_parts.append("\nDataflöde:")
        for i, node in enumerate(nodes[:10], 1):  # Max 10 första noderna
            summary = self.extract_node_summary(node)
            logic_parts.append(f"{i}. {summary}")

        if len(nodes) > 10:
            logic_parts.append(f"... och {len(nodes) - 10} till noder")

        return "\n".join(logic_parts)

    def generate_workflow_description(self, workflow_data: Dict[str, Any]) -> str:
        """Genererar en naturlig beskrivning av vad workflowen gör."""
        name = workflow_data.get('name', 'Unknown Workflow')
        nodes = workflow_data.get('nodes', [])

        # Identifiera huvudfunktioner baserat på node-typer
        triggers = [n for n in nodes if 'trigger' in n.get('type', '').lower() or 'webhook' in n.get('type', '').lower()]
        ai_nodes = [n for n in nodes if 'openai' in n.get('type', '').lower() or 'langchain' in n.get('type', '').lower()]
        database_nodes = [n for n in nodes if 'postgres' in n.get('type', '').lower() or 'mysql' in n.get('type', '').lower()]
        api_nodes = [n for n in nodes if 'http' in n.get('type', '').lower()]

        description_parts = []

        if triggers:
            trigger_type = triggers[0].get('type', '')
            if 'webhook' in trigger_type:
                description_parts.append("som tar emot HTTP requests")
            elif 'googleDrive' in trigger_type:
                description_parts.append("som triggas av nya filer i Google Drive")
            elif 'cron' in trigger_type or 'schedule' in trigger_type:
                description_parts.append("som körs på ett schema")

        if ai_nodes:
            description_parts.append("använder AI för att processa data")

        if database_nodes:
            description_parts.append("lagrar och hämtar data från databas")

        if api_nodes:
            description_parts.append("integrerar med externa API:er")

        # Identifiera specifika integrationer
        integrations = set()
        for node in nodes:
            node_type = node.get('type', '')
            if 'clickUp' in node_type:
                integrations.add('ClickUp')
            if 'github' in node_type:
                integrations.add('GitHub')
            if 'googleCalendar' in node_type:
                integrations.add('Google Calendar')
            if 'slack' in node_type:
                integrations.add('Slack')

        if integrations:
            description_parts.append(f"integrerar med {', '.join(integrations)}")

        if description_parts:
            return f"en workflow {', '.join(description_parts)}"
        else:
            return "en automatiseringsworkflow"

    def create_training_example(self, workflow_data: Dict[str, Any]) -> Dict[str, str]:
        """Skapar ett Q&A-par från workflow-data."""
        name = workflow_data.get('name', 'Unknown Workflow')
        description = self.generate_workflow_description(workflow_data)
        logic = self.extract_workflow_logic(workflow_data)

        # Extrahera alla AI prompts
        all_prompts = []
        for node in workflow_data.get('nodes', []):
            prompts = self.extract_ai_prompts(node)
            all_prompts.extend(prompts)

        # Bygg prompt
        prompt = f"Skapa en n8n workflow för {description}"

        # Bygg completion
        completion_parts = [
            f"Här är en workflow-konfiguration för '{name}':\n",
            logic
        ]

        if all_prompts:
            completion_parts.append("\nViktiga AI prompts i workflowen:")
            for i, prompt_text in enumerate(all_prompts[:3], 1):  # Max 3 prompts
                # Begränsa längd
                truncated = prompt_text[:300] + "..." if len(prompt_text) > 300 else prompt_text
                completion_parts.append(f"{i}. {truncated}")

        # Lägg till node-konfigurationer (sampling)
        nodes = workflow_data.get('nodes', [])
        if nodes:
            completion_parts.append("\nExempel på node-konfigurationer:")
            for node in nodes[:3]:  # Första 3 noderna
                node_info = {
                    'name': node.get('name'),
                    'type': node.get('type'),
                    'parameters': node.get('parameters', {})
                }
                # Ta bort credentials från parameters
                if 'credentials' in node_info['parameters']:
                    node_info['parameters'].pop('credentials', None)
                completion_parts.append(f"\n{json.dumps(node_info, indent=2, ensure_ascii=False)}")

        completion = "\n".join(completion_parts)

        return {
            'prompt': prompt,
            'completion': completion
        }

    def process_workflow_file(self, filepath: Path) -> bool:
        """Processar en enskild workflow-fil."""
        try:
            print(f"Processar: {filepath.name}")

            with open(filepath, 'r', encoding='utf-8') as f:
                workflow_data = json.load(f)

            # Skapa training example
            example = self.create_training_example(workflow_data)
            self.training_examples.append(example)

            self.processed_count += 1
            return True

        except json.JSONDecodeError as e:
            print(f"  ERROR: Kunde inte parsa JSON i {filepath.name}: {e}")
            self.error_count += 1
            return False
        except Exception as e:
            print(f"  ERROR: Fel vid processning av {filepath.name}: {e}")
            self.error_count += 1
            return False

    def convert_all_workflows(self):
        """Konverterar alla workflows i katalogen."""
        print(f"\nSöker efter workflows i: {self.workflow_dir}")
        print("-" * 60)

        # Hitta alla JSON-filer
        json_files = list(self.workflow_dir.glob('*.json'))

        if not json_files:
            print("Inga JSON-filer hittades!")
            return

        print(f"Hittade {len(json_files)} workflow-filer\n")

        # Processa varje fil
        for filepath in sorted(json_files):
            self.process_workflow_file(filepath)

        print("\n" + "-" * 60)
        print(f"Processning klar!")
        print(f"  Framgångsrika: {self.processed_count}")
        print(f"  Fel: {self.error_count}")
        print(f"  Training examples: {len(self.training_examples)}")

    def save_training_data(self):
        """Sparar training data till JSONL-fil."""
        if not self.training_examples:
            print("\nIngen training data att spara!")
            return

        print(f"\nSparar training data till: {self.output_file}")

        # Skapa output-katalog om den inte finns
        self.output_file.parent.mkdir(parents=True, exist_ok=True)

        # Skriv JSONL-fil
        with open(self.output_file, 'w', encoding='utf-8') as f:
            for example in self.training_examples:
                json_line = json.dumps(example, ensure_ascii=False)
                f.write(json_line + '\n')

        print(f"Sparade {len(self.training_examples)} training examples")

        # Skriv även en pretty-printed version för inspektion
        pretty_file = self.output_file.with_suffix('.json')
        with open(pretty_file, 'w', encoding='utf-8') as f:
            json.dump(self.training_examples, f, indent=2, ensure_ascii=False)

        print(f"Sparade även pretty-printed version: {pretty_file}")

    def print_sample_examples(self, num_samples: int = 2):
        """Skriver ut några exempel för inspektion."""
        if not self.training_examples:
            return

        print("\n" + "=" * 60)
        print("EXEMPEL PÅ TRAINING DATA")
        print("=" * 60)

        for i, example in enumerate(self.training_examples[:num_samples], 1):
            print(f"\nEXEMPEL {i}:")
            print("-" * 60)
            print(f"PROMPT:\n{example['prompt']}\n")
            print(f"COMPLETION (förkortad):\n{example['completion'][:500]}...")
            print("-" * 60)


def main():
    # Konfigurera sökvägar
    workflow_dir = "/home/ai-server/01_PROJECTS/01_AI-VIBE-WORLD/RÖR EJ WORKFLOW"
    output_file = "/home/ai-server/01_PROJECTS/01_AI-VIBE-WORLD/scripts/training_data.jsonl"

    print("=" * 60)
    print("n8n Workflow to LoRA Training Data Converter")
    print("=" * 60)

    # Skapa converter och kör
    converter = WorkflowToTrainingConverter(workflow_dir, output_file)
    converter.convert_all_workflows()
    converter.save_training_data()
    converter.print_sample_examples(num_samples=2)

    print("\n" + "=" * 60)
    print("KLART!")
    print("=" * 60)
    print(f"\nTraining data sparad i:")
    print(f"  - JSONL: {output_file}")
    print(f"  - JSON:  {output_file.replace('.jsonl', '.json')}")
    print("\nNästa steg:")
    print("  1. Inspektera training_data.json för att verifiera kvalitet")
    print("  2. Använd training_data.jsonl för LoRA fine-tuning")
    print("  3. Justera prompts och completions vid behov")


if __name__ == "__main__":
    main()
