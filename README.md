# BorgiaToGadzby

Ce script permet le transfére des utilisateurs Borgia vers Gadzby.

## 1. Utilisation

### Prérequis

- Python3
- Docker

Installer les dépendances Python :
```bash
pip install -r requirements.txt
```

#### Dump Borgia

Pour créer un dump de la base de donnée Borgia :

```bash
pg_dump -Fc --no-owner -no-privileges > backup_borgia.dump
```

si l'instance Borgia est hébergé dans un conteneur LXC :

```bash
sudo lxc-attach -n [NOM_CONTENEUR] -- su - postgres -c "pg_dump -Fc --no-owner --no-privileges [NOM_BDD]" > backup_borgia.dump 
```

### Exécution de la migration

Une fois le dump créé et placé à la racine du projet, exécutez le script de migration adapté à votre système :

#### Sur Windows (PowerShell)

```powershell
.\migrate.ps1
```

Le script va :
1. Créer un conteneur Docker avec PostgreSQL
2. Restaurer le dump Borgia dans une base de données temporaire
3. Exécuter le script Python pour transformer et migrer les données
4. Importer les données dans Gadzby
5. Arrêter et nettoyer le conteneur

#### Sur Linux/macOS (Bash)

```bash
bash ./migrate.sh
```

Le processus est identique au script Windows.

### Configuration

Avant d'exécuter la migration, vérifiez les paramètres dans `script.py` :

- **STAGING_URI** : URI de connexion à la base de données Borgia temporaire (créée par le conteneur Docker)
- **TARGET_URI** : URI de connexion à la base de données Gadzby cible
- **CLEAN_TARGET** : Mettre à `True` pour vider la table cible avant l'import

Par défaut :
- Staging DB : `postgresql://postgres:password@localhost:5434/old_staging_db`
- Target DB : `postgresql://postgres:password@localhost:5432/gadzby`

### Transformations des données

Le script effectue les transformations suivantes :

| Colonne Borgia | Colonne Gadzby | Transformation |
|---|---|---|
| last_name | nom | Renommage simple |
| first_name | prenom | Renommage simple |
| family | nums | Renommage simple |
| surname | bucque | Renommage simple |
| is_active | is_asleep | Logique inversée (NOT) |
| campus | tabagnss | Conversion en majuscules, validation contre liste valide |
| balance | balance | Conversion en centimes (×100) |
| year | - | Calcul : year - 1800 |
| - | promss | Génération : `{tabagnss}{proms_year}` |
| password | password_hash | Renommage simple |
| email | email | Minuscules obligatoires |
| username | username | Minuscules obligatoires |
| avatar | image | Renommage simple |

### Nettoyage des données

Le script applique également :

- **Suppression de l'utilisateur "admin"**
- **Normalisation des emails et usernames** : conversion en minuscules, suppression des chaînes vides
- **Génération des usernames manquants** : format `nom.prenom`
- **Validation des codes campus** : seuls `ME`, `CL`, `CH`, `KA`, `PA`, `BO`, `LI`, `AN` sont acceptés
- **Suppression des doublons** : par email et username (garde la première occurrence)
- **Suppression des lignes invalides** : celles sans `promss` valide ou sans `year`

