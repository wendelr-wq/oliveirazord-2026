import time
import requests

class CapMonsterSolver:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.create_task_url = "https://api.capmonster.cloud/createTask"
        self.get_result_url = "https://api.capmonster.cloud/getTaskResult"

    def resolver_captcha(self, base64_image: str, threshold: int = 80, 
                                max_attempts: int = 10, poll_interval: float = 0.5) -> str:
        """
        Tenta resolver a MESMA imagem até atingir a confiança desejada.
        Só paga quando consegue uma resposta de alta qualidade.
        """
        for tentativa in range(1, max_attempts + 1):
            if tentativa > 1:
                print(f"   🔄 Re-tentativa {tentativa-1}/{max_attempts-1} (threshold={threshold/100:.0%})")
            
            # Criar tarefa com threshold
            task_payload = {
                "clientKey": self.api_key,
                "task": {
                    "type": "ImageToTextTask",
                    "body": base64_image,
                    "recognizingThreshold": threshold
                }
            }
            
            response = requests.post(self.create_task_url, json=task_payload)
            result = response.json()
            
            # Se erro por baixa confiança, tenta de novo
            if result.get("errorId") != 0:
                error = result.get('errorDescription', '')
                if "UNSOLVABLE" in error:
                    if tentativa == 1:
                        print(f"   ⚠️  Confiança abaixo de {threshold/100:.0%}, ajustando...")
                    continue
                else:
                    raise Exception(f"Erro inesperado: {error}")
            
            task_id = result["taskId"]
            
            # Aguardar resultado
            start_time = time.time()
            while time.time() - start_time < 30:
                time.sleep(poll_interval)
                poll = requests.post(self.get_result_url, 
                                     json={"clientKey": self.api_key, "taskId": task_id})
                res = poll.json()
                
                if res.get("status") == "ready":
                    texto = res.get("solution", {}).get("text", "")
                    print(f"   🔑 Resposta: {texto}")
                    return texto
                elif res.get("status") == "processing":
                    continue  # silencioso
                elif res.get("errorId") != 0:
                    raise Exception(f"Erro: {res.get('errorDescription')}")
            
            print(f"   ⏱️  Timeout")
        
        raise Exception(f"❌ Não conseguiu resolver após {max_attempts} tentativas")
