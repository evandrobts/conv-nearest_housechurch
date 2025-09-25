# Localizador de Igrejas Caseiras - Convergência Campinas

Este projeto é uma solução completa para ajudar as pessoas a encontrarem as **Igrejas Caseiras** da Igreja Convergência de Campinas. Ele é composto por três partes principais: um painel de administração para gerenciar o cadastro das igrejas, uma aplicação web de busca para o público e um backend (API) robusto que integra as funcionalidades.

-----

### Visão Geral da Arquitetura

O sistema opera no **Google Cloud Platform (GCP)**, utilizando serviços como o **Cloud Run** para hospedar a API e o **Firestore** para o banco de dados.

A arquitetura do projeto é dividida da seguinte forma:

1.  **Backend (`main.py`):** Uma API Python que lida com a lógica de geocodificação e busca no banco de dados.
2.  **Banco de Dados (Firestore):** Armazena todas as informações das igrejas, como endereços, contatos e coordenadas.
3.  **Frontend (HTML/JS):** Duas versões da aplicação de busca e um painel de administração para gerenciar os dados.

-----

### Frontend

O frontend é composto por três arquivos HTML, cada um com uma finalidade específica. Todos utilizam **Tailwind CSS** para estilização e JavaScript puro para a lógica de interação.

  * **`admin.html` - Painel de Administração:**
    Este é o painel restrito para administradores. Ele permite o gerenciamento completo das igrejas cadastradas. O login é feito com uma conta Google e somente e-mails autorizados têm acesso. As principais funcionalidades incluem:

      * **Visualização em Tabela:** Lista todas as igrejas de forma paginada e com opções de busca e ordenação por nome, endereço, CEP, dia/hora e contato.
      * **Cadastro e Atualização:** É possível cadastrar novas igrejas ou atualizar registros existentes. A latitude e longitude do endereço são verificadas e preenchidas automaticamente ao clicar no botão "Preencher lat/lon". Isso elimina a necessidade de saber as coordenadas de antemão, tornando o cadastro mais fácil e preciso.
      * **Exclusão:** Permite a exclusão de registros de igrejas.
      * **Exportação:** Possibilita exportar todos os dados filtrados em um arquivo CSV.

  * **`localizador_int.html` - Localizador Interno:**
    Esta versão é destinada aos membros da igreja. Ela oferece uma busca detalhada e completa. O usuário pode buscar por endereço ou usar a geolocalização do dispositivo. Os resultados exibem o endereço exato da igreja, CEP e um link direto para o Google Maps com a localização precisa.

  * **`localizador_ext.html` - Localizador Externo:**
    Projetado para o público em geral, este localizador prioriza a privacidade. Embora a lógica de busca e cálculo de distância seja a mesma do localizador interno, os resultados são exibidos de forma mais genérica. Em vez do endereço completo, o card da igreja mostra apenas o **bairro e a cidade**. O link para o Google Maps também é modificado para apontar para a área geral, e não para o endereço exato da residência.

-----

### Backend (API)

A API é o cérebro do sistema, responsável por toda a lógica de processamento de dados. Ela é implementada em Python usando o **Functions Framework** e o **Flask**, e é executada em um ambiente sem servidor no **Google Cloud Run**.

  * **Geocodificação (`geocode_and_find_nearest_2`):** A função principal da API recebe uma solicitação com um endereço, CEP, ou coordenadas de latitude e longitude. Ela utiliza a **Google Maps Geocoding API** para converter endereços em coordenadas precisas, se necessário. O código está otimizado para lidar com endereços brasileiros, adicionando um *bias* para a região.

  * **Cálculo de Distância:** Uma vez que as coordenadas do usuário são obtidas, a API calcula a distância em quilômetros até cada igreja usando a **fórmula de Haversine**.

  * **Busca e Ordenação:** A API consulta a coleção `churches` no Firestore, buscando apenas os registros marcados como `active: true`. Os resultados são então filtrados por um raio máximo de distância (opcional) e ordenados da igreja mais próxima para a mais distante.

-----

### Banco de Dados e População Inicial

O projeto utiliza o **Google Firestore** como banco de dados NoSQL, ideal para este tipo de aplicação por sua escalabilidade e flexibilidade. As igrejas são armazenadas em uma coleção chamada `churches`.

Para a configuração inicial, foi criado um arquivo `seed_churches.json` que pode ser usado para popular o banco de dados. Este arquivo contém uma lista de objetos JSON, cada um representando uma igreja com todos os campos necessários, como `name`, `address`, `cep`, `day`, `time`, `contact`, `lat`, `lon` e `active`. A utilização de um arquivo de *seed* é uma prática comum para garantir que o ambiente de desenvolvimento e produção tenham dados iniciais consistentes.

-----

### Instalação e Configuração

#### Pré-requisitos

  * **Python 3.12** ou superior.
  * Uma conta do **Google Cloud** com o **Firestore** e a **Google Maps Geocoding API** habilitados.
  * **Docker** (opcional, para rodar o backend em um contêiner).

#### Variáveis de Ambiente

O backend requer uma chave da API do Google Maps. Configure a variável de ambiente `Maps_API_KEY` com sua chave.

```
GOOGLE_MAPS_API_KEY="SUA_CHAVE_AQUI"
```

#### Dependências

As dependências do Python estão listadas no arquivo `requirements.txt`. Instale-as usando pip:

```bash
pip install -r requirements.txt
```

#### Como Rodar o Backend com Docker

O `Dockerfile` empacota a aplicação em um contêiner, facilitando a implantação.

1.  **Construa a imagem Docker:**
    ```bash
    docker build -t localizador-igrejas .
    ```
2.  **Execute o contêiner localmente:**
    ```bash
    docker run -p 8080:8080 --env GOOGLE_MAPS_API_KEY="SUA_CHAVE_AQUI" localizador-igrejas
    ```
