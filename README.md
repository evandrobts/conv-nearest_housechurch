# Localizador de Igrejas Caseiras - Convergência Campinas

Este projeto é uma ferramenta para ajudar as pessoas a encontrarem as **Igrejas Caseiras** da Igreja Convergência de Campinas. Ele foi construído em três partes: um painel de administração, uma aplicação web de busca e um backend que conecta tudo.

## Visão Geral do Projeto

### 1\. Aplicação de Busca

A aplicação de busca, acessível via web, permite que qualquer pessoa encontre as reuniões mais próximas de sua localização.

  * **Versão Externa:** Oferece busca por endereço ou geolocalização, mas mantém a privacidade, mostrando apenas o bairro e a cidade da igreja, sem a localização exata.
  * **Versão Interna:** É a versão completa, usada pelos membros da igreja, que exibe o endereço e a localização exata das igrejas caseiras.

### 2\. Painel de Administração

O painel de administração é uma interface web restrita, usada para gerenciar o cadastro das igrejas.

  * **Acesso Seguro:** Apenas administradores autorizados com contas Google específicas podem fazer login.
  * **Gestão de Dados:** Permite visualizar, adicionar, editar e excluir informações de cada igreja, incluindo nome, contato, endereço, dia e horário das reuniões, e coordenadas geográficas.
  * **Funcionalidades:** Inclui busca, ordenação, paginação e a opção de exportar os dados para um arquivo CSV.

### 3\. Backend (API)

O backend é uma API que processa as solicitações de busca.

  * **Geocodificação Inteligente:** Converte endereços e CEPs em coordenadas de latitude e longitude usando a **API do Google Maps**. Ele foi otimizado para a região de Campinas, o que torna a busca mais precisa, mesmo com endereços ambíguos.
  * **Cálculo de Distância:** A API calcula a distância entre a localização do usuário e cada igreja usando a **fórmula de Haversine**.
  * **Consulta de Dados:** Busca as igrejas ativas no banco de dados **Google Firestore**.
  * **Filtros Avançados:** Filtra os resultados com base na distância máxima e retorna as igrejas mais próximas, já ordenadas.

## Tecnologias Usadas

  * **Frontend:** HTML, CSS com **Tailwind CSS**, e JavaScript puro.
  * **Backend:** Python com **Flask** e **Functions Framework**.
  * **Banco de Dados:** **Google Firestore**.
  * **APIs Externas:** **Google Maps Platform** para geocodificação e links de localização.
  * **Infraestrutura:** A API foi projetada para rodar em ambientes de função sem servidor (serverless), como o **Google Cloud Run**.
  * **Contêineres:** **Docker** para empacotar a aplicação backend.

## Instalação e Configuração

### Pré-requisitos

Certifique-se de ter instalado:

  * **Python 3.12** ou superior.
  * Uma conta do **Google Cloud** com o **Firestore** e a **Google Maps Geocoding API** ativados.
  * **Docker** (opcional, para rodar o backend localmente ou em contêiner).

### Variáveis de Ambiente

O backend precisa de uma chave de API para funcionar. Crie um arquivo `.env` ou configure a variável de ambiente:

```
GOOGLE_MAPS_API_KEY="SUA_CHAVE_AQUI"
```

### Dependências

As dependências do Python estão no arquivo `requirements.txt`. Instale-as usando pip:

```bash
pip install -r requirements.txt
```

### Como Rodar o Backend com Docker

O `Dockerfile` prepara o ambiente para a aplicação.

1.  **Construa a imagem:**
    ```bash
    docker build -t localizador-igrejas .
    ```
2.  **Rode o contêiner:**
    ```bash
    docker run -p 8080:8080 --env GOOGLE_MAPS_API_KEY="SUA_CHAVE_AQUI" localizador-igrejas
    ```
