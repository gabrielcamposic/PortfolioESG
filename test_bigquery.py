from google.cloud import bigquery

client = bigquery.Client()

print(f"Projeto: {client.project}")
print("Conexão com BigQuery estabelecida com sucesso!")

# Listar datasets (estará vazio se não tiver nenhum)
datasets = list(client.list_datasets())
print(f"Datasets encontrados: {len(datasets)}")