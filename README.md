# Extraction PV Zeendoc vers OR

Ce projet automatise le traitement des PV d'expertise stockes dans une armoire Zeendoc:

1. authentification securisee a l'API Zeendoc;
2. parcours des PV retournes par la recherche Zeendoc enregistree `24`;
3. recuperation des indices Zeendoc utiles;
4. recuperation du texte OCR Zeendoc via `Ihm/View/Get_Texte_Document.php`;
5. extraction automatique des sections `Liste des fournitures` ou `Liste des pieces`;
6. generation d'un ordre de reparation structure en JSON, HTML imprimable et PDF;
7. optionnellement, upload du PDF OR dans Zeendoc et marquage du PV comme traite.

## Configuration

Installer d'abord les dependances:

```powershell
python -m pip install -e .
```

Les identifiants ne sont jamais codes en dur. Definir les variables d'environnement:

```powershell
$env:ZEENDOC_BASE_URL = "https://armoires.zeendoc.com/carrosserie_cyril_minatchy/api/v4"
$env:ZEENDOC_LOGIN = "votre_login"
$env:ZEENDOC_PASSWORD = "votre_mot_de_passe"
$env:ZEENDOC_BINDER_ID = "coll_1"
```

`ZEENDOC_BINDER_ID` correspond au `collId` Zeendoc: l'identifiant du classeur/armoire dans lequel la recherche est executee. Son format est generalement `coll_1`, `coll_2`, etc. Si vous indiquez seulement `1`, le programme le transforme automatiquement en `coll_1`.
Si `ZEENDOC_BASE_URL` est renseignee avec l'URL de l'armoire sans `/api/v4`, le programme ajoute automatiquement `/api/v4`.

Les colonnes d'indices a recuperer peuvent etre ajustees:

```powershell
$env:ZEENDOC_WANTED_COLUMNS = "Res_Id,Upload_Id,custom_t2,custom_t3,custom_t4,custom_t5,custom_d4,custom_d1,custom_t6,custom_t8,custom_t1,custom_t7,custom_t9,custom_t10,custom_t11,custom_t12"
```

Pour recuperer les champs de classement metier, il faut utiliser les noms techniques Zeendoc exacts. Les lister avec:

```powershell
python -m or_extractor.cli --list-fields
```

Si la premiere colonne est vide ou douteuse, afficher le JSON brut:

```powershell
python -m or_extractor.cli --list-fields-raw
```

Puis ajouter les champs voulus. Avec les libelles visibles dans cette armoire, essayer par exemple:

```powershell
$env:ZEENDOC_WANTED_COLUMNS = "Res_Id,Upload_Id,custom_t2,custom_t5,custom_d4,custom_d1,custom_t6,custom_t8,custom_t1,custom_t7,custom_t10,custom_t11,custom_t12"
```

Les valeurs recuperees sont stockees dans `document.fields` dans le JSON de sortie. Le programme remplit `client`, `sinistre`, `expert`, `immatriculation` et `date` uniquement depuis les champs de classement renvoyes par Zeendoc.
Les champs complementaires `custom_t10` (`Liste des fournitures`), `custom_t11` (`Designation des travaux`) et `custom_t12` (`Observations`) sont alimentes depuis le texte OCR du PV, affiches dans l'OR, puis envoyes dans l'indexation Zeendoc lors de l'upload de l'OR.

Par defaut, le traitement ne recupere pas tous les documents du classeur: il utilise la recherche Zeendoc enregistree `24`, via `POST /binders/{collId}/documents/search` et le champ API `savedQueryId`.
Pour la definir explicitement:

```powershell
$env:ZEENDOC_SEARCH_ID = "24"
```

Le programme ne telecharge pas le PDF pour l'analyse: il recupere le texte OCR via `Ihm/View/Get_Texte_Document.php?Coll_Id=...&Res_Id=...`.

Pour l'upload de l'OR genere, le programme copie les principaux champs de classement du PV et force par defaut le type de document `Ordre de réparation`:

```powershell
$env:ZEENDOC_OR_DOCUMENT_TYPE_FIELD = "custom_n3"
$env:ZEENDOC_OR_DOCUMENT_TYPE_VALUE = "18"
```

Le marquage du PV source est volontairement optionnel. Par defaut, le champ utilise est `custom_n1` avec la valeur `1`, correspondant a `Ordre de réparation = OK` dans cette armoire. Si vous voulez utiliser un autre champ, surchargez-le:

```powershell
$env:ZEENDOC_PROCESSED_FIELD = "custom_n1"
$env:ZEENDOC_PROCESSED_VALUE = "1"
```

## Lancement

```powershell
python -m or_extractor.cli --output-dir .\out
```

Options utiles:

```powershell
python -m or_extractor.cli --binder-id 123 --search-id 24 --limit 20 --output-dir .\out
```

Generer localement, puis remonter l'OR PDF dans Zeendoc:

```powershell
python -m or_extractor.cli --output-dir .\out --upload-or
```

Remonter l'OR et marquer le PV source comme traite:

```powershell
python -m or_extractor.cli --output-dir .\out --upload-or --mark-processed
```

Changer le champ de marquage au lancement:

```powershell
python -m or_extractor.cli --output-dir .\out --upload-or --mark-processed --mark-field custom_n1 --mark-value 1
```

## API HTTP

Le projet expose aussi une API pour un bouton Zeendoc ou un appel serveur:

```text
GET /health
GET /generate-or?res_id=39
GET /generate-or?res_id=39&download=true
GET /process-search?search_id=24
```

Par defaut, l'API upload l'OR genere dans Zeendoc (`OR_API_UPLOAD_OR=true`) mais ne marque pas le PV comme traite (`OR_API_MARK_PROCESSED=false`). Ces deux comportements peuvent etre changes par variable d'environnement ou ponctuellement dans l'URL:

```text
/generate-or?res_id=39&upload_or=true&mark_processed=true
```

Pour traiter une recherche Zeendoc complete:

```text
/process-search?search_id=24
/process-search?search_id=24&limit=2
```

Pour proteger l'endpoint, definir `OR_EXTRACTOR_API_TOKEN`. Le token peut etre transmis par query string, pratique pour un bouton Zeendoc:

```text
https://votre-app.fly.dev/generate-or?res_id={Res_Id}&token=VOTRE_TOKEN
```

Pour un bouton ou lien qui lance la recherche 24:

```text
https://votre-app.fly.dev/process-search?search_id=24&token=VOTRE_TOKEN
```

ou par header HTTP:

```text
Authorization: Bearer VOTRE_TOKEN
```

En local:

```powershell
python -m uvicorn or_extractor.web_app:app --host 0.0.0.0 --port 8080
```

## Deploiement Fly.io

Les fichiers `Dockerfile` et `fly.toml` preparent le projet pour Fly.io. Le nom d'application dans `fly.toml` est `carrosserie-minatchy-or`; changez-le si besoin.

Configurer les secrets:

```powershell
fly secrets set ZEENDOC_BASE_URL="https://armoires.zeendoc.com/carrosserie_cyril_minatchy/api/v4"
fly secrets set ZEENDOC_LOGIN="votre_login"
fly secrets set ZEENDOC_PASSWORD="votre_mot_de_passe"
fly secrets set ZEENDOC_BINDER_ID="coll_1"
fly secrets set ZEENDOC_SEARCH_ID="24"
fly secrets set OR_EXTRACTOR_API_TOKEN="un_token_long_et_secret"
```

Options utiles:

```powershell
fly secrets set ZEENDOC_PROCESSED_FIELD="custom_n1"
fly secrets set ZEENDOC_PROCESSED_VALUE="1"
fly secrets set ZEENDOC_OR_DOCUMENT_TYPE_FIELD="custom_n3"
fly secrets set ZEENDOC_OR_DOCUMENT_TYPE_VALUE="18"
fly secrets set OR_API_UPLOAD_OR="true"
fly secrets set OR_API_MARK_PROCESSED="false"
```

Deployer:

```powershell
fly deploy
```

Tester:

```powershell
fly status
curl https://carrosserie-minatchy-or.fly.dev/health
```

Pour diagnostiquer une reponse Zeendoc qui ne contient pas les champs de classement ou le lien PDF direct attendu:

```powershell
$env:ZEENDOC_DEBUG_PAYLOAD_DIR = ".\debug-zeendoc"
python -m or_extractor.cli --output-dir .\out
```

Pour tester les champs de classement d'un document precis sans generer d'OR:

```powershell
python -m or_extractor.cli --debug-document 39 --output-dir .\out
```

Pour tester une variante de `wantedColumns`:

```powershell
python -m or_extractor.cli --debug-document 39 --debug-wanted-columns "Res_Id,Upload_Id,custom_t2,custom_t5,custom_d4,custom_t6,custom_t1"
```

## Sorties

Pour chaque PV exploitable, le traitement produit:

- `or_<id>.json`: donnees structurees de l'ordre de reparation;
- `or_<id>.html`: document imprimable contenant indices et lignes extraites.
- `or_<id>.pdf`: ordre de reparation PDF pret a imprimer ou transmettre.
- `source-text/ocr_<id>_raw.txt`: texte OCR brut recupere depuis Zeendoc.
- `source-text/ocr_<id>.txt`: texte OCR nettoye utilise par le parseur.
- `report.json`: bilan global avec documents traites, ignores, erreurs et nombre de lignes extraites.

## Structure

- `or_extractor/zeendoc_client.py`: connexion, recherche et recuperation des documents Zeendoc.
- `or_extractor/pv_parser.py`: detection des sections, extraction multi-pages jusqu'au marqueur `TOTAL`.
- `or_extractor/or_generator.py`: formatage des donnees et rendu JSON/HTML.
- `or_extractor/or_pdf_generator.py`: rendu PDF professionnel de l'OR.
- `or_extractor/pipeline.py`: orchestration complete.
- `or_extractor/cli.py`: interface en ligne de commande.
- `or_extractor/web_app.py`: API HTTP pour bouton Zeendoc et deploiement Fly.io.
- `Dockerfile` / `fly.toml`: configuration de deploiement Fly.io.
