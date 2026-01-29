import pandas as pd
import os
import plotly.express as px
import dash
from dash import dcc, html, Input, Output, State
from thefuzz import process
from difflib import get_close_matches

# --- CONFIGURATION & DONNÉES ---
chemin_dossier = "./Datas"
columns = ["DATE", "MONTH", "YEAR", "CIES", "PARCOURS", "ENTREPRISE", "APPORTEUR", "TC", "TM", "FS"]
months_order = ["JANVIER", "FEVRIER", "MAR", "APRIL", "MAY", "JUIN", "JUILLET", "AOUT", "SEPTEMBRE", "October", "Novembre", "Decembre"]

COLORS = {
    'background': '#F4F7F9',
    'card': '#FFFFFF',
    'text': '#1A1A1A',
    'palette': ['#2C3E50', '#54A0FF', '#00D2D3', '#A29BFE', '#FCA110']
}

# --- FONCTIONS DE TRAITEMENT ---

def map_similar_columns(df, target_columns, threshold=0.6):
    new_columns = {}
    already_used_targets = set() # Pour suivre les noms déjà attribués
    
    for col in df.columns:
        col_cleaned = str(col).strip()
        
        # On cherche le match le plus proche
        matches = get_close_matches(col_cleaned, target_columns, n=1, cutoff=threshold)
        
        if matches:
            target = matches[0]
            # SI le nom cible est déjà pris par une autre colonne, on garde l'original
            if target not in already_used_targets:
                new_columns[col] = target
                already_used_targets.add(target)
            else:
                new_columns[col] = col # Évite de créer un doublon
        else:
            new_columns[col] = col
            
    return df.rename(columns=new_columns)

def auto_clean_names(df, column_name, threshold=85):
    counts = df[column_name].value_counts()
    unique_names = counts.index.tolist()
    mapping = {}
    already_processed = set()
    for name in unique_names:
        if name in already_processed: continue
        matches = process.extract(name, unique_names, limit=None)
        for match, score in matches:
            if score >= threshold:
                mapping[match] = name
                already_processed.add(match)
    return df[column_name].map(mapping)

def clean_df(df):

        # 1. On force tout en string et on gère les vides
    df['APPORTEUR'] = df['APPORTEUR'].astype(str).replace('nan', 'INCONNU').str.upper().str.strip()
    
    # Nettoyage robuste du Chiffre d'Affaires
    df["TC"] = pd.to_numeric(df["TC"].astype(str).str.replace(r'[\s\u00A0]', '', regex=True).str.replace(',', '.'), errors='coerce').fillna(0)
    df = df[df["TC"] > 0].copy()
    
    df["ENTREPRISE"] = df["ENTREPRISE"].fillna("NON SPECIFIE").str.upper().str.strip()
    df["YEAR"] = df["YEAR"].astype(str)
    df['APPORTEUR'] = auto_clean_names(df, 'APPORTEUR')
    return df

# --- CHARGEMENT DES DONNÉES ---
data_aggr = pd.DataFrame()
if os.path.exists(chemin_dossier):
    for nom_fichier in os.listdir(chemin_dossier):
        if nom_fichier.endswith(('.xlsx', '.xls')):
            chemin_complet = os.path.join(chemin_dossier, nom_fichier)
            year = nom_fichier.split(".")[0].split(" ")[-1]
            
            for n, month in enumerate(months_order, 1):
                # --- DANS VOTRE BOUCLE DE LECTURE ---
                try:
                    df = pd.read_excel(chemin_complet, sheet_name=month)
                    
                    # 1. Supprime les colonnes totalement vides (souvent à droite dans Excel)
                    df = df.dropna(axis=1, how='all')
                    
                    # 2. Supprime les doublons de noms bruts (ex: deux colonnes "TVA")
                    df = df.loc[:, ~df.columns.duplicated()]
                    
                    # 3. Renommage intelligent (version corrigée ci-dessus)
                    df = map_similar_columns(df, columns)
                    
                    # 4. Sécurité : si après renommage il y a encore des doublons (cas rare)
                    df = df.loc[:, ~df.columns.duplicated()]

                    # Ajout des métadonnées
                    df["MONTH_LABEL"] = month
                    df["MONTH_IDX"] = str(n).zfill(2)
                    df["YEAR"] = str(year)
                    
                    # Vérification de la colonne TC
                    if "TC" not in df.columns:
                        df["TC"] = 0

                    data_aggr = pd.concat([data_aggr, df], axis=0, ignore_index=True)
                    print(f"Succès : {month} {year}")
                    
                except Exception as e:
                    print(f"Erreur sur le mois {month} dans {nom_fichier} : {e}")

data_aggr = clean_df(data_aggr)

ordre_des_mois = ["JANVIER", "FEVRIER", "MAR", "APRIL", "MAY", "JUIN", 
                  "JUILLET", "AOUT", "SEPTEMBRE", "October", "Novembre", "Decembre"]

data_aggr['MONTH_LABEL'] = pd.Categorical(
    data_aggr['MONTH_LABEL'], 
    categories=ordre_des_mois, 
    ordered=True
)

# 3. Optionnel : On trie le DataFrame pour être sûr
data_aggr = data_aggr.sort_values(['YEAR', 'MONTH_LABEL'])


# --- DASH APP ---
app = dash.Dash(__name__)

# Style pour les blocs (Cards) occupant toute la largeur
STRATE_STYLE = {
    'backgroundColor': '#FFFFFF',
    'padding': '30px',
    'borderRadius': '20px',
    'boxShadow': '0 8px 20px rgba(0,0,0,0.05)',
    'marginBottom': '40px'
}

app = dash.Dash(__name__)

app.layout = html.Div(style={'backgroundColor': '#F4F7F9', 'fontFamily': 'Segoe UI, Arial', 'padding': '40px'}, children=[
    
    html.H1("Système de Pilotage Commercial", 
            style={'textAlign': 'center', 'marginBottom': '50px', 'fontWeight': '800', 'color': '#1A1A1A'}),

    # --- STRATE 1 : ANALYSE PARETO ET INDICATEURS ---
    html.Div(style=STRATE_STYLE, children=[
        html.H3("🎯 1. Analyse de Pareto (80/20) & Indicateurs Clés", style={'marginBottom': '20px'}),
        
        # Filtre dédié pour cette section
        html.Div(style={'maxWidth': '400px', 'marginBottom': '30px'}, children=[
            html.Label("Sélectionner l'Année d'Analyse :", style={'fontWeight': 'bold'}),
            dcc.Dropdown(
                id='year-pareto-filter', 
                options=[{'label': f"Année {y}", 'value': y} for y in sorted(data_aggr['YEAR'].unique())] + [{'label': 'Toutes les années', 'value': 'ALL'}], 
                value='ALL', clearable=False
            ),
        ]),

        # 1. Graphique Pareto (Stacked - Pleine largeur)
        dcc.Graph(id='graph-pareto', style={'height': '500px', 'marginBottom': '40px'}),

        # 2 & 3. Indicateurs (Sur la même ligne)
        html.Div(style={'display': 'flex', 'gap': '30px'}, children=[
            # Indicateur Clients
            html.Div(style={'flex': '1', 'textAlign': 'center', 'padding': '30px', 'backgroundColor': '#F8F9FA', 'borderRadius': '20px', 'border': '1px solid #E9ECEF'}, children=[
                html.H4("Nombre de Clients Uniques", style={'color': '#636E72', 'marginBottom': '10px'}),
                html.Div(id='kpi-clients', style={'fontSize': '48px', 'fontWeight': '800', 'color': COLORS['palette'][0]})
            ]),
            # Indicateur CA
            html.Div(style={'flex': '1', 'textAlign': 'center', 'padding': '30px', 'backgroundColor': '#F8F9FA', 'borderRadius': '20px', 'border': '1px solid #E9ECEF'}, children=[
                html.H4("Chiffre d'Affaires Total", style={'color': '#636E72', 'marginBottom': '10px'}),
                html.Div(id='kpi-ca', style={'fontSize': '48px', 'fontWeight': '800', 'color': COLORS['palette'][1]})
            ])
        ])
    ]),

    # --- STRATE 2 : ANALYSE DÉTAILLÉE (SUNBURST) ---
    html.Div(style=STRATE_STYLE, children=[
        html.H3("📂 2. Analyse par Apporteur & Détail Entreprises", style={'marginBottom': '20px'}),
        html.Div(style={'display': 'flex', 'gap': '20px', 'marginBottom': '20px'}, children=[
            html.Div(style={'flex': '1'}, children=[
                html.Label("Choisir Apporteur :", style={'fontWeight': 'bold'}),
                dcc.Dropdown(
                    id='sun-app-filter',
                    options=[{'label': 'TOUS LES APPORTEURS', 'value': 'ALL'}] + [{'label': x, 'value': x} for x in sorted(data_aggr['APPORTEUR'].unique())],
                    value='ALL', clearable=False
                ),
            ]),
            html.Div(style={'flex': '2'}, children=[
                html.Label("Rechercher des Entreprises spécifiques :", style={'fontWeight': 'bold'}),
                dcc.Dropdown(id='sun-ent-filter', multi=True, placeholder="Tapez le nom d'une entreprise..."),
            ]),
        ]),
        dcc.Graph(id='graph-sunburst', style={'height': '550px'})
    ]),

    # --- STRATE 3 : SAISONNALITÉ (Ligne 3) ---
    html.Div(style=STRATE_STYLE, children=[
        html.H3("📈 3. Saisonalité : Comparaison Annuelle", style={'marginBottom': '20px'}),
        html.Div(style={'maxWidth': '400px', 'marginBottom': '20px'}, children=[
            html.Label("Historique de l'Apporteur :", style={'fontWeight': 'bold'}),
            dcc.Dropdown(
                id='time-app-filter',
                options=[{'label': 'TOTAL AGENCE', 'value': 'ALL'}] + [{'label': x, 'value': x} for x in sorted(data_aggr['APPORTEUR'].unique())],
                value='ALL', clearable=False
            ),
        ]),
        dcc.Graph(id='graph-time-evolution', style={'height': '450px'})
    ]),

    # --- STRATE 4 : BENCHMARK (Ligne 4) ---
    html.Div(style=STRATE_STYLE, children=[
        html.H3("⚔️ 4. Benchmark : Comparaison entre Apporteurs", style={'marginBottom': '20px'}),
        html.Div(style={'display': 'flex', 'gap': '20px', 'marginBottom': '20px'}, children=[
            html.Div(style={'flex': '1'}, children=[
                html.Label("Année d'analyse :", style={'fontWeight': 'bold'}),
                dcc.Dropdown(
                    id='comp-year-filter', 
                    options=[{'label': y, 'value': y} for y in sorted(data_aggr['YEAR'].unique())], 
                    value=sorted(data_aggr['YEAR'].unique())[-1], clearable=False
                )
            ]),
            html.Div(style={'flex': '3'}, children=[
                html.Label("Apporteurs à comparer :", style={'fontWeight': 'bold'}),
                dcc.Dropdown(
                    id='comp-apps-filter', multi=True, 
                    options=[{'label': x, 'value': x} for x in sorted(data_aggr['APPORTEUR'].unique())], 
                    value=sorted(data_aggr['APPORTEUR'].unique())[:2]
                )
            ]),
        ]),
        dcc.Graph(id='graph-comparison', style={'height': '450px'})
    ]),

    # --- STRATE 5 : RÉPARTITION CA (Ligne 5 - STACKED) ---
    html.Div(style=STRATE_STYLE, children=[
        html.H3("💰 4. Répartition Globale du Chiffre d'Affaires", style={'marginBottom': '20px'}),
        html.Div(style={'maxWidth': '400px', 'marginBottom': '10px'}, children=[
            html.Label("Sélectionner l'Année :", style={'fontWeight': 'bold'}),
            dcc.Dropdown(
                id='year-ca-filter', 
                options=[{'label': f"Année {y}", 'value': y} for y in sorted(data_aggr['YEAR'].unique())] + [{'label': 'Historique Global', 'value': 'ALL'}], 
                value='ALL', clearable=False
            ),
        ]),
        dcc.Graph(id='graph-pie-ca', style={'height': '500px'})
    ]),

    # --- STRATE 6 : RÉPARTITION VOLUME (Ligne 6 - STACKED) ---
    html.Div(style=STRATE_STYLE, children=[
        html.H3("📊 5. Répartition Globale du Volume de Ventes", style={'marginBottom': '20px'}),
        html.Div(style={'maxWidth': '400px', 'marginBottom': '10px'}, children=[
            html.Label("Sélectionner l'Année :", style={'fontWeight': 'bold'}),
            dcc.Dropdown(
                id='year-vol-filter', 
                options=[{'label': f"Année {y}", 'value': y} for y in sorted(data_aggr['YEAR'].unique())] + [{'label': 'Historique Global', 'value': 'ALL'}], 
                value='ALL', clearable=False
            ),
        ]),
        dcc.Graph(id='graph-pie-vol', style={'height': '500px'})
    ]),
])

# --- CALLBACK 1 : CHAÎNAGE DES FILTRES (APPORTEUR -> ENTREPRISES) ---
# Ce callback ne s'occupe QUE de mettre à jour la liste des entreprises
@app.callback(
    [Output('sun-ent-filter', 'options'),
     Output('sun-ent-filter', 'value')],
    [Input('sun-app-filter', 'value')]
)
def update_enterprise_list(selected_app):
    if selected_app == 'ALL':
        ents = sorted(data_aggr['ENTREPRISE'].unique())
    else:
        ents = sorted(data_aggr[data_aggr['APPORTEUR'] == selected_app]['ENTREPRISE'].unique())
    return [{'label': x, 'value': x} for x in ents], []

# --- CALLBACK 2 : UNIQUE PILOTE POUR TOUS LES GRAPHES ET KPI ---
# Ce callback gère tous les calculs et tous les affichages
@app.callback(
    [Output('graph-sunburst', 'figure'),
     Output('graph-time-evolution', 'figure'),
     Output('graph-comparison', 'figure'),
     Output('graph-pie-ca', 'figure'),
     Output('graph-pie-vol', 'figure'),
     Output('graph-pareto', 'figure'),
     Output('kpi-clients', 'children'),
     Output('kpi-ca', 'children')],
    [Input('sun-app-filter', 'value'),
     Input('sun-ent-filter', 'value'),
     Input('time-app-filter', 'value'),
     Input('comp-year-filter', 'value'),
     Input('comp-apps-filter', 'value'),
     Input('year-ca-filter', 'value'),
     Input('year-vol-filter', 'value'),
     Input('year-pareto-filter', 'value')] # L'entrée yr_pareto est bien ici
)
def update_dashboard(sun_app, sun_ents, time_app, comp_yr, comp_apps, yr_ca, yr_vol, yr_pareto):
    
    # 1. LOGIQUE PARETO & KPI (Basée sur le filtre yr_pareto)
    df_p = data_aggr if yr_pareto == 'ALL' else data_aggr[data_aggr['YEAR'] == str(yr_pareto)]
    
    # Calcul Pareto
    pareto_data = df_p.groupby('ENTREPRISE')['TC'].sum().sort_values(ascending=False).reset_index()
    total_tc_pareto = pareto_data['TC'].sum()
    pareto_data['cum_perc'] = 100 * (pareto_data['TC'].cumsum() / total_tc_pareto)

    import plotly.graph_objects as go
    fig_pareto = go.Figure()
    fig_pareto.add_trace(go.Bar(x=pareto_data['ENTREPRISE'].head(25), y=pareto_data['TC'].head(25), 
                                name="CA", marker_color=COLORS['palette'][1]))
    fig_pareto.add_trace(go.Scatter(x=pareto_data['ENTREPRISE'].head(25), y=pareto_data['cum_perc'].head(25), 
                                    name="% Cumulé", yaxis="y2", line=dict(color='#E74C3C', width=3)))
    
    fig_pareto.update_layout(
        title="Top 25 Clients (Pareto)",
        yaxis=dict(title="CA (Fcfa)"),
        yaxis2=dict(title="%", overlaying="y", side="right", range=[0, 105]),
        template="plotly_white"
    )

    # Valeurs des Indicateurs
    kpi_clients = f"{df_p['ENTREPRISE'].nunique()}"
    kpi_ca = f"{total_tc_pareto:,.0f} Fcfa".replace(',', ' ')

    # 2. LOGIQUE SUNBURST
    df_s = data_aggr.copy()
    if sun_app != 'ALL': df_s = df_s[df_s['APPORTEUR'] == sun_app]
    if sun_ents: df_s = df_s[df_s['ENTREPRISE'].isin(sun_ents)]
    fig_sun = px.sunburst(df_s, path=['YEAR', 'ENTREPRISE'], values='TC', color_discrete_sequence=px.colors.qualitative.Prism)

    # 3. LOGIQUE SAISONNALITÉ
    df_t = data_aggr if time_app == 'ALL' else data_aggr[data_aggr['APPORTEUR'] == time_app]
    df_t_g = df_t.groupby(['YEAR', 'MONTH_IDX', 'MONTH_LABEL'], observed=True)['TC'].sum().reset_index()
    fig_time = px.line(df_t_g, x='MONTH_LABEL', y='TC', color='YEAR', markers=True, line_shape='spline')
    fig_time.update_xaxes(categoryorder='array', categoryarray=months_order)

    # 4. LOGIQUE BENCHMARK
    df_c = data_aggr[data_aggr['YEAR'] == str(comp_yr)]
    if comp_apps: df_c = df_c[df_c['APPORTEUR'].isin(comp_apps)]
    df_c_g = df_c.groupby(['APPORTEUR', 'MONTH_LABEL'], observed=True)['TC'].sum().reset_index()
    fig_comp = px.line(df_c_g, x='MONTH_LABEL', y='TC', color='APPORTEUR', markers=True, line_shape='spline')
    fig_comp.update_xaxes(categoryorder='array', categoryarray=months_order)

    # 5. LOGIQUE DONUTS
    df_pie_ca = data_aggr if yr_ca == 'ALL' else data_aggr[data_aggr['YEAR'] == str(yr_ca)]
    fig_ca_pie = px.pie(df_pie_ca, values='TC', names='APPORTEUR', hole=0.6)
    fig_ca_pie.update_traces(textinfo='none', hovertemplate="<b>%{label}</b><br>CA: %{value}Fcfa<br>%{percent}")

    df_pie_vol = data_aggr if yr_vol == 'ALL' else data_aggr[data_aggr['YEAR'] == str(yr_vol)]
    df_vol_counts = df_pie_vol.groupby('APPORTEUR').size().reset_index(name='NB_VENTES')
    fig_vol_pie = px.pie(df_vol_counts, values='NB_VENTES', names='APPORTEUR', hole=0.6)
    fig_vol_pie.update_traces(textinfo='none', hovertemplate="<b>%{label}</b><br>Ventes: %{value}<br>%{percent}")

    # STYLING FINAL
    for f in [fig_sun, fig_time, fig_comp, fig_ca_pie, fig_vol_pie, fig_pareto]:
        f.update_layout(margin=dict(t=40, b=20, l=20, r=20), paper_bgcolor='rgba(0,0,0,0)', title_x=0.5)

    return fig_sun, fig_time, fig_comp, fig_ca_pie, fig_vol_pie, fig_pareto, kpi_clients, kpi_ca

if __name__ == '__main__':
    app.run(debug=True)