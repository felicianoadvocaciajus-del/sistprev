/**
 * SistPrev — Frontend JavaScript
 * Comunicação com API FastAPI em /api/v1/
 */

const API = '/api/v1';

// ── Estado global ─────────────────────────────────────────────────────────
const state = {
  segurado: null,
  vinculos: [],
  beneficiosAnteriores: [],
  ultimoCalculo: null,
  ultimoPlanejamento: null,
  beneficiosCNIS: [],
  editandoVinculoIdx: -1,
  contribEditando: [],
};

// ── Inicialização ─────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  carregarDoLocalStorage();
  preencherDerHoje();
});

function preencherDerHoje() {
  const hoje = new Date().toLocaleDateString('pt-BR');
  ['calc-der', 'plan-der', 'teto-der', 'at-atualizacao'].forEach(id => {
    const el = document.getElementById(id);
    if (el && !el.value) el.value = hoje;
  });
}

// ── LocalStorage ─────────────────────────────────────────────────────────
function salvarNoLocalStorage() {
  try {
    const dados = {
      dados_pessoais: {
        nome: document.getElementById('seg-nome').value,
        data_nascimento: document.getElementById('seg-dn').value,
        sexo: document.getElementById('seg-sexo').value,
        cpf: document.getElementById('seg-cpf').value.replace(/\D/g, '') || null,
        nit: document.getElementById('seg-nit').value.replace(/\D/g, '') || null,
      },
      vinculos: state.vinculos,
      beneficios_anteriores: state.beneficiosAnteriores || [],
    };
    localStorage.setItem('sistprev_segurado', JSON.stringify(dados));
    if (state.ultimoCalculo) {
      localStorage.setItem('sistprev_calculo', JSON.stringify(state.ultimoCalculo));
    }
    if (state.beneficiosCNIS?.length) {
      localStorage.setItem('sistprev_beneficios', JSON.stringify(state.beneficiosCNIS));
    }
    if (state.modoCalculo) {
      localStorage.setItem('sistprev_modo', state.modoCalculo);
    }
    document.getElementById('save-indicator').textContent = '💾 Salvo';
    document.getElementById('save-indicator').style.color = '#6ee7b7';
  } catch (e) { /* silencioso */ }
}

function carregarDoLocalStorage() {
  try {
    const raw = localStorage.getItem('sistprev_segurado');
    if (!raw) return;
    const dados = JSON.parse(raw);
    preencherFormularioSegurado(dados);
    state.vinculos = dados.vinculos || [];
    state.beneficiosAnteriores = dados.beneficios_anteriores || [];
    renderizarVinculos();

    const calc = localStorage.getItem('sistprev_calculo');
    if (calc) state.ultimoCalculo = JSON.parse(calc);

    // Restaurar benefícios e modo de cálculo
    const benRaw = localStorage.getItem('sistprev_beneficios');
    if (benRaw) {
      state.beneficiosCNIS = JSON.parse(benRaw);
      configurarModoPlanejamento();
    }

    document.getElementById('save-indicator').textContent = '💾 Dados carregados';
    setTimeout(() => { document.getElementById('save-indicator').textContent = '💾 Salvo'; }, 2000);
  } catch (e) { /* silencioso */ }
}

// Auto-salva ao editar qualquer campo do segurado
['seg-nome','seg-cpf','seg-dn','seg-sexo','seg-nit'].forEach(id => {
  document.getElementById(id)?.addEventListener('change', salvarNoLocalStorage);
});

document.getElementById('btn-limpar-dados')?.addEventListener('click', () => {
  if (!confirm('Apagar todos os dados do segurado e vinculos? Esta ação não pode ser desfeita.')) return;
  localStorage.removeItem('sistprev_segurado');
  localStorage.removeItem('sistprev_calculo');
  localStorage.removeItem('sistprev_beneficios');
  localStorage.removeItem('sistprev_modo');
  ['seg-nome','seg-cpf','seg-dn','seg-nit'].forEach(id => document.getElementById(id).value = '');
  document.getElementById('seg-sexo').value = 'MASCULINO';
  state.vinculos = [];
  state.beneficiosAnteriores = [];
  state.ultimoCalculo = null;
  state.beneficiosCNIS = [];
  state.modoCalculo = 'PLANEJAMENTO';
  state.aposentadoriaAtiva = null;
  state.beneficioIndeferido = null;
  resetarModoPlanejamento();
  renderizarVinculos();
  document.getElementById('resumo-segurado').classList.add('hidden');
  toast('Dados apagados', 'info');
});

// ── Roteamento ────────────────────────────────────────────────────────────
document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', e => {
    e.preventDefault();
    const page = item.dataset.page;
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    item.classList.add('active');
    document.getElementById(`page-${page}`)?.classList.add('active');
  });
});

// ── Tabs ──────────────────────────────────────────────────────────────────
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    const tabId = tab.dataset.tab;
    const parent = tab.closest('.page') || document;
    parent.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    parent.querySelectorAll('.tab-content').forEach(tc => tc.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(`tab-${tabId}`)?.classList.add('active');
  });
});

// ── Upload CNIS ───────────────────────────────────────────────────────────
document.getElementById('input-cnis').addEventListener('change', async e => {
  const file = e.target.files[0];
  if (!file) return;
  const statusEl = document.getElementById('status-cnis');
  const cardEl = document.getElementById('card-cnis');
  statusEl.innerHTML = '<span class="loader"></span> Processando...';
  cardEl.classList.remove('success', 'error');
  const fd = new FormData();
  fd.append('arquivo', file);
  try {
    const res = await fetch(`${API}/upload/cnis`, { method: 'POST', body: fd });
    const data = await res.json();
    if (data.sucesso && data.segurado) {
      state.vinculos = data.segurado.vinculos || [];
      state.beneficiosAnteriores = data.segurado.beneficios_anteriores || [];
      cardEl.classList.add('success');
      const dp = data.segurado.dados_pessoais;
      const nVinc = data.segurado.vinculos?.length || 0;
      const nContrib = data.segurado.vinculos?.reduce((s,v) => s + (v.contribuicoes?.length||0), 0) || 0;
      const nBenef = data.beneficios?.length || 0;
      const avisoOcr = data.avisos?.find(a => a.includes('OCR')) ? ' (via OCR)' : '';
      statusEl.innerHTML = `<div style="text-align:left;">
        <div style="font-size:14px;font-weight:700;">✅ ${dp.nome}${avisoOcr}</div>
        <div style="font-size:11px;color:#374151;margin-top:4px;">
          CPF: ${dp.cpf || '—'} | Nasc: ${dp.data_nascimento || '—'} | Sexo: ${dp.sexo || '—'}
        </div>
        <div style="font-size:11px;color:#065f46;margin-top:2px;">
          ${nVinc} vínculo(s) | ${nContrib} contribuição(ões) | ${nBenef} benefício(s)
        </div>
        ${data.avisos?.length ? `<div style="font-size:10px;color:#92400e;margin-top:2px;">${data.avisos.slice(0,3).join(' · ')}</div>` : ''}
      </div>`;
      // Mostrar análise especial de todos os vínculos do CNIS
      if (data.analise_especial?.length) {
        const especiaisCnis = data.analise_especial.filter(v => v.especial?.possivel);
        if (especiaisCnis.length) {
          statusEl.innerHTML += renderizarAnaliseVinculos(data.analise_especial, null, null, null, null, 'CNIS');
          toast(`CNIS: ${especiaisCnis.length} vinculo(s) com indicativo de atividade especial!`, 'info', 8000);
        }
      }
      preencherFormularioSegurado(data.segurado);
      renderizarVinculos();
      salvarNoLocalStorage();
      toast('CNIS importado com sucesso!', 'success');
      // Armazenar benefícios para análise de revisão no planejamento
      state.beneficiosCNIS = data.beneficios || [];
      // DETECÇÃO INTELIGENTE DE MODO: Aposentado / Indeferido / Planejamento
      state.modoCalculo = 'PLANEJAMENTO'; // padrão
      state.aposentadoriaAtiva = null;
      state.beneficioIndeferido = null;
      if (data.beneficios?.length) {
        // Espécies de aposentadoria RGPS
        const especiesApos = [41,42,46,57,99];
        const ativos = data.beneficios.filter(b => b.situacao === 'ATIVO' && especiesApos.includes(Number(b.especie_codigo)));
        const indeferidos = data.beneficios.filter(b => b.situacao === 'INDEFERIDO');

        if (ativos.length) {
          const b = ativos[0];
          state.modoCalculo = 'REVISAO';
          state.aposentadoriaAtiva = b;
          toast(`🏆 MODO REVISÃO ATIVADO: ${b.especie} (espécie ${b.especie_codigo}) concedida em ${b.data_inicio || '?'}. O sistema vai recalcular na DER original.`, 'info', 15000);
          // DER do planejamento = DER original da aposentadoria
          if (b.data_inicio) {
            const planDer = document.getElementById('plan-der');
            planDer.value = b.data_inicio;
            // Mostrar campo DER original (travado)
            const derOrigGroup = document.getElementById('plan-der-original-group');
            const derOrigInput = document.getElementById('plan-der-original');
            if (derOrigGroup && derOrigInput) {
              derOrigInput.value = b.data_inicio;
              derOrigGroup.style.display = '';
            }
            // Atualizar labels e hints
            const derLabel = document.getElementById('plan-der-label');
            if (derLabel) derLabel.textContent = 'DER para Cálculo *';
            const derHint = document.getElementById('plan-der-hint');
            if (derHint) {
              derHint.style.display = 'block';
              derHint.textContent = 'Pré-preenchido com a DER da aposentadoria. Para reafirmação (Tema 995 STJ), altere para a data desejada.';
            }
            // Preencher abas de revisão
            ['teto-dib', 'at-dib'].forEach(id => {
              const el = document.getElementById(id);
              if (el && !el.value) el.value = b.data_inicio;
            });
            ['teto-der', 'pcd-der', 'rev-mb-der', 'rev-esp-der', 'rev-vt-der'].forEach(id => {
              const el = document.getElementById(id);
              if (el && !el.value) el.value = b.data_inicio;
            });
            // Preencher RMI nas revisões
            if (b.rmi || state.rmiCarta) {
              const rmiVal = b.rmi || state.rmiCarta;
              ['rev-mb-rmi', 'rev-esp-rmi'].forEach(id => {
                const el = document.getElementById(id);
                if (el && !el.value) el.value = fmtDecimal(rmiVal);
              });
            }
          }
          // Atualizar título e subtítulo
          document.getElementById('plan-titulo').textContent = 'Revisão de Aposentadoria';
          document.getElementById('plan-subtitulo').textContent = 'Segurado já aposentado. O sistema recalcula na DER original para verificar se o INSS concedeu o melhor benefício.';
          // Painel fixo de benefício ativo
          atualizarPainelBeneficioAtivo(b);
          // Alerta visual
          const alertaEl = document.getElementById('plan-modo-alerta');
          alertaEl.className = 'card';
          alertaEl.style.cssText = 'border:3px solid #dc2626;background:#fef2f2;padding:16px;margin-bottom:16px;';
          alertaEl.innerHTML = `
            <div style="display:flex;align-items:center;gap:12px;">
              <div style="font-size:32px;">🔍</div>
              <div>
                <div style="font-size:15px;font-weight:800;color:#991b1b;">MODO REVISÃO — Segurado já aposentado</div>
                <div style="font-size:13px;color:#7f1d1d;margin-top:4px;">
                  <strong>${b.especie}</strong> (espécie ${b.especie_codigo}) concedida em <strong>${b.data_inicio}</strong>
                  ${b.rmi ? ` — RMI: <strong>R$ ${b.rmi}</strong>` : ''}
                </div>
                <div style="font-size:12px;color:#374151;margin-top:6px;">
                  O sistema vai recalcular a RMI na DER original por TODAS as regras e comparar com o que o INSS concedeu.
                  Se houver regra mais vantajosa, será indicada a revisão com fundamentação legal.
                </div>
                <div style="font-size:11px;color:#6b7280;margin-top:4px;">
                  Art. 687, IN PRES/INSS 128/2022 — Princípio do Melhor Benefício (STF Tema 334, RE 630.501/RS)
                </div>
              </div>
            </div>`;
        } else if (indeferidos.length) {
          const b = indeferidos[0];
          state.modoCalculo = 'INDEFERIDO';
          state.beneficioIndeferido = b;
          toast(`❌ MODO INDEFERIDO: ${b.especie} negado em ${b.data_inicio || '?'}. O sistema vai verificar se havia direito na DER do pedido.`, 'info', 15000);
          if (b.data_inicio) {
            const planDer = document.getElementById('plan-der');
            planDer.value = b.data_inicio;
            const derOrigGroup = document.getElementById('plan-der-original-group');
            const derOrigInput = document.getElementById('plan-der-original');
            if (derOrigGroup && derOrigInput) {
              derOrigInput.value = b.data_inicio;
              derOrigGroup.style.display = '';
            }
            const derLabel = document.getElementById('plan-der-label');
            if (derLabel) derLabel.textContent = 'DER do Pedido Negado *';
            const derHint = document.getElementById('plan-der-hint');
            if (derHint) {
              derHint.style.display = 'block';
              derHint.textContent = 'Data do requerimento indeferido. Para reafirmação da DER (Tema 995 STJ), altere para data posterior.';
            }
            ['teto-der', 'pcd-der'].forEach(id => {
              const el = document.getElementById(id);
              if (el && !el.value) el.value = b.data_inicio;
            });
          }
          document.getElementById('plan-titulo').textContent = 'Análise de Benefício Indeferido';
          document.getElementById('plan-subtitulo').textContent = 'Benefício negado pelo INSS. O sistema verifica se o segurado tinha direito na DER e calcula os atrasados.';
          const alertaEl = document.getElementById('plan-modo-alerta');
          alertaEl.className = 'card';
          alertaEl.style.cssText = 'border:3px solid #f59e0b;background:#fffbeb;padding:16px;margin-bottom:16px;';
          alertaEl.innerHTML = `
            <div style="display:flex;align-items:center;gap:12px;">
              <div style="font-size:32px;">⚠️</div>
              <div>
                <div style="font-size:15px;font-weight:800;color:#92400e;">BENEFÍCIO INDEFERIDO — Verificar direito na DER</div>
                <div style="font-size:13px;color:#78350f;margin-top:4px;">
                  <strong>${b.especie}</strong> (espécie ${b.especie_codigo}) indeferido em <strong>${b.data_inicio || '?'}</strong>
                </div>
                <div style="font-size:12px;color:#374151;margin-top:6px;">
                  O sistema vai calcular se o segurado preenchia os requisitos na DER do pedido negado.
                  Se sim, os atrasados são devidos desde essa data em ação judicial.
                  Se não, o sistema buscará a data mais próxima em que os requisitos serão preenchidos (Reafirmação da DER — Tema 995 STJ).
                </div>
              </div>
            </div>`;
        } else {
          // Benefícios que não são aposentadoria (ex: auxílio-doença)
          const hoje = new Date();
          const planDer = document.getElementById('plan-der');
          if (!planDer.value) planDer.value = `${String(hoje.getDate()).padStart(2,'0')}/${String(hoje.getMonth()+1).padStart(2,'0')}/${hoje.getFullYear()}`;
        }
      }
      // Sugerir DER na tela de Calcular Beneficio
      atualizarSugestoesDER();
      if (data.avisos?.length) toast('Avisos: ' + data.avisos.join('; '), 'info');
    } else {
      cardEl.classList.add('error');
      statusEl.textContent = '❌ ' + (data.erros?.join('; ') || 'Falha no processamento');
    }
  } catch(err) {
    cardEl.classList.add('error');
    statusEl.textContent = '❌ Erro: ' + (err.message || 'Falha de conexão');
    console.error('Upload CNIS erro:', err);
  }
  e.target.value = '';
});

document.getElementById('input-carta').addEventListener('change', async e => {
  const file = e.target.files[0]; if (!file) return;
  const statusEl = document.getElementById('status-carta');
  const cardEl = document.getElementById('card-carta');
  statusEl.innerHTML = '<span class="loader"></span> Processando...';
  const fd = new FormData(); fd.append('arquivo', file);
  try {
    const res = await fetch(`${API}/upload/carta-concessao`, { method: 'POST', body: fd });
    const data = await res.json();
    if (res.ok && data.sucesso) {
      cardEl.classList.add('success');
      const avisoOcrCarta = data.avisos?.find(a => a.includes('OCR')) ? ' (via OCR)' : '';
      statusEl.innerHTML = `<div style="text-align:left;">
        <div style="font-size:14px;font-weight:700;">✅ ${data.descricao_especie || 'Benefício ' + (data.especie||'')}${avisoOcrCarta}</div>
        <div style="font-size:11px;color:#374151;margin-top:4px;">
          NB: ${data.numero_beneficio || '—'} | Espécie: ${data.especie || '—'} | Nome: ${data.nome_segurado || '—'}
        </div>
        <div style="font-size:12px;color:#065f46;font-weight:700;margin-top:2px;">
          DIB: ${data.dib || '—'} | RMI: R$ ${fmtDecimal(data.rmi)} ${data.salario_beneficio ? '| SB: R$ ' + fmtDecimal(data.salario_beneficio) : ''}
        </div>
        ${data.fator_previdenciario ? `<div style="font-size:10px;color:#6b7280;margin-top:2px;">FP: ${data.fator_previdenciario} | Coef: ${data.coeficiente || '—'}</div>` : ''}
        ${data.avisos?.length ? `<div style="font-size:10px;color:#92400e;margin-top:2px;">${data.avisos.join(' · ')}</div>` : ''}
      </div>`;
      if (data.dib) { ['teto-dib','at-dib'].forEach(id => { const el=document.getElementById(id); if(el) el.value = data.dib; }); }
      if (data.rmi) {
        ['teto-rmi','at-rmi'].forEach(id => { const el=document.getElementById(id); if(el) el.value = fmtDecimal(data.rmi); });
        // Gravar RMI da Carta no state para uso na revisão
        state.rmiCarta = data.rmi;
        // Se tem benefício ativo do CNIS sem RMI, preencher com a da Carta
        if (state.aposentadoriaAtiva) {
          if (!state.aposentadoriaAtiva.rmi) state.aposentadoriaAtiva.rmi = data.rmi;
          atualizarPainelBeneficioAtivo(state.aposentadoriaAtiva);
        }
        // Atualizar benefícios CNIS com RMI da carta para revisão
        if (state.beneficiosCNIS?.length) {
          const ativo = state.beneficiosCNIS.find(b => b.situacao === 'ATIVO');
          if (ativo && (!ativo.rmi || ativo.rmi === '0')) ativo.rmi = data.rmi;
        }
        localStorage.setItem('sistprev_rmi_carta', data.rmi);
      }
      toast('Carta de Concessão processada!', 'success');
    } else {
      cardEl.classList.add('error');
      const msg = data.erro || data.detail || 'Falha ao processar documento';
      statusEl.textContent = '❌ ' + msg;
      if (data.avisos && data.avisos.length) toast(data.avisos.join('; '), 'warning');
    }
  } catch(err) { cardEl.classList.add('error'); statusEl.textContent = '❌ Erro: ' + (err.message || 'conexão'); }
  e.target.value = '';
});

document.getElementById('input-ctps').addEventListener('change', async e => {
  const file = e.target.files[0]; if (!file) return;
  const statusEl = document.getElementById('status-ctps');
  const cardEl = document.getElementById('card-ctps');
  statusEl.innerHTML = '<span class="loader"></span> Analisando CTPS e pesquisando atividades especiais...';
  const fd = new FormData(); fd.append('arquivo', file);
  try {
    const res = await fetch(`${API}/upload/ctps`, { method: 'POST', body: fd });
    if (res.ok) {
      const data = await res.json();
      cardEl.classList.add('success');
      statusEl.innerHTML = renderizarAnaliseVinculos(data.vinculos || [], data.nome, data.cpf, data.pis_pasep, data.avisos, 'CTPS');
      const especiais = (data.vinculos||[]).filter(v => v.especial?.possivel);
      if (especiais.length) {
        toast(`CTPS: ${especiais.length} vinculo(s) com indicativo de atividade especial!`, 'success', 8000);
      } else {
        toast(`CTPS importada: ${data.vinculos?.length || 0} vinculos`, 'success');
      }
    } else {
      const errCtps = await res.json().catch(() => ({}));
      cardEl.classList.add('error');
      statusEl.textContent = '❌ ' + (errCtps.detail || 'Falha ao processar');
    }
  } catch(err) { cardEl.classList.add('error'); statusEl.textContent = '❌ Erro: ' + (err.message || 'conexão'); }
  e.target.value = '';
});

// ── Upload PPP ───────────────────────────────────────────────────────────
document.getElementById('input-ppp').addEventListener('change', async e => {
  const file = e.target.files[0]; if (!file) return;
  const statusEl = document.getElementById('status-ppp');
  const cardEl = document.getElementById('card-ppp');
  statusEl.innerHTML = '<span class="loader"></span> Analisando PPP e buscando jurisprudencia...';
  const fd = new FormData(); fd.append('arquivo', file);
  try {
    const res = await fetch(`${API}/upload/ppp`, { method: 'POST', body: fd });
    const data = await res.json();
    if (data.sucesso) {
      cardEl.classList.add('success');
      // Guardar no state para cruzamento
      if (!state.ppps) state.ppps = [];
      state.ppps.push(data);
      statusEl.innerHTML = renderizarPPP(data);
      const nAgentes = data.exposicoes?.length || 0;
      toast(`PPP processado: ${nAgentes} agente(s) nocivo(s) encontrado(s)!`, nAgentes > 0 ? 'success' : 'info', 8000);
    } else {
      cardEl.classList.add('error');
      statusEl.textContent = '❌ ' + (data.erro || 'Falha ao processar PPP');
    }
  } catch(err) { cardEl.classList.add('error'); statusEl.textContent = '❌ Erro: ' + (err.message || 'conexao'); }
  e.target.value = '';
});

// ── Upload LTCAT / Documentos Comprobatorios ─────────────────────────────
document.getElementById('input-ltcat').addEventListener('change', async e => {
  const file = e.target.files[0]; if (!file) return;
  const statusEl = document.getElementById('status-ltcat');
  const cardEl = document.getElementById('card-ltcat');
  statusEl.innerHTML = '<span class="loader"></span> Analisando documento...';
  const fd = new FormData(); fd.append('arquivo', file);
  // Detectar tipo pelo nome do arquivo
  const nomeUpper = file.name.toUpperCase();
  let tipo = 'LTCAT';
  if (nomeUpper.includes('CAT')) tipo = 'CAT';
  if (nomeUpper.includes('LAUDO')) tipo = 'LAUDO';
  if (nomeUpper.includes('DIRBEN')) tipo = 'DIRBEN';
  if (nomeUpper.includes('ATESTADO')) tipo = 'ATESTADO';
  fd.append('tipo', tipo);
  try {
    const res = await fetch(`${API}/upload/documento-comprobatorio`, { method: 'POST', body: fd });
    const data = await res.json();
    if (data.sucesso) {
      cardEl.classList.add('success');
      if (!state.documentosComprobatorios) state.documentosComprobatorios = [];
      state.documentosComprobatorios.push(data);
      statusEl.innerHTML = renderizarDocComprobatorio(data);
      toast(`${tipo} processado: ${data.agentes_encontrados?.length || 0} agente(s) detectado(s)`, 'success');
    } else {
      cardEl.classList.add('error');
      statusEl.textContent = '❌ ' + (data.erro || 'Falha ao processar');
    }
  } catch(err) { cardEl.classList.add('error'); statusEl.textContent = '❌ Erro: ' + (err.message || 'conexao'); }
  e.target.value = '';
});

function renderizarPPP(data) {
  let html = `<div style="text-align:left;max-height:450px;overflow-y:auto;">`;
  html += `<div style="font-size:14px;font-weight:700;color:#dc2626;margin-bottom:6px;">⚠️ PPP — Perfil Profissiografico</div>`;

  // Trabalhador
  if (data.trabalhador?.nome) {
    html += `<div style="font-size:12px;"><strong>${data.trabalhador.nome}</strong>`;
    if (data.trabalhador.cpf) html += ` | CPF: ${data.trabalhador.cpf}`;
    if (data.trabalhador.nit) html += ` | NIT: ${data.trabalhador.nit}`;
    html += `</div>`;
  }

  // Empresa
  if (data.empresa?.razao_social) {
    html += `<div style="font-size:11px;color:#374151;margin-top:4px;">`;
    html += `<strong>Empresa:</strong> ${data.empresa.razao_social}`;
    if (data.empresa.cnpj) html += ` | CNPJ: ${data.empresa.cnpj}`;
    if (data.empresa.cnae) html += ` | CNAE: ${data.empresa.cnae}`;
    if (data.empresa.grau_risco) html += ` | Grau de Risco: <strong style="color:#dc2626">${data.empresa.grau_risco}</strong>`;
    html += `</div>`;
  }

  // Vinculo
  if (data.vinculo?.cargo) {
    html += `<div style="font-size:11px;margin-top:3px;">`;
    html += `<strong>Cargo:</strong> ${data.vinculo.cargo}`;
    if (data.vinculo.cbo) html += ` | CBO: ${data.vinculo.cbo}`;
    if (data.vinculo.setor) html += ` | Setor: ${data.vinculo.setor}`;
    html += `</div>`;
    if (data.vinculo.data_admissao) {
      html += `<div style="font-size:10px;color:#6b7280;">Periodo: ${data.vinculo.data_admissao} — ${data.vinculo.data_demissao || 'atual'}</div>`;
    }
  }

  // Exposicoes — A PARTE MAIS IMPORTANTE
  if (data.exposicoes?.length) {
    html += `<div style="margin-top:8px;border-top:2px solid #dc2626;padding-top:6px;">`;
    html += `<div style="font-size:12px;font-weight:800;color:#dc2626;">AGENTES NOCIVOS COMPROVADOS (${data.exposicoes.length})</div>`;
    for (const exp of data.exposicoes) {
      const agNome = (exp.agente_nocivo || '').replace(/_/g, ' ');
      html += `<div style="background:#fef2f2;border-left:3px solid #dc2626;padding:6px 10px;margin-top:4px;border-radius:0 6px 6px 0;">`;
      html += `<div style="font-weight:700;font-size:12px;color:#991b1b;">${agNome}</div>`;
      if (exp.codigo_agente) html += `<div style="font-size:10px;">Codigo Anexo IV: ${exp.codigo_agente}</div>`;
      if (exp.intensidade) html += `<div style="font-size:10px;">Intensidade: <strong>${exp.intensidade}</strong></div>`;
      if (exp.data_inicio) html += `<div style="font-size:10px;">Periodo: ${exp.data_inicio} — ${exp.data_fim || 'atual'}</div>`;
      const epi = exp.epi_eficaz === true ? '✅ Sim' : exp.epi_eficaz === false ? '❌ Nao' : '—';
      const epc = exp.epc_eficaz === true ? '✅ Sim' : exp.epc_eficaz === false ? '❌ Nao' : '—';
      html += `<div style="font-size:10px;">EPI eficaz: ${epi} | EPC eficaz: ${epc}</div>`;
      if (exp.ca_epi) html += `<div style="font-size:10px;">CA do EPI: ${exp.ca_epi}</div>`;
      html += `</div>`;
    }
    html += `</div>`;
  }

  // Jurisprudencias
  if (data.jurisprudencias?.length) {
    html += `<div style="margin-top:8px;">`;
    html += `<div style="font-size:11px;font-weight:700;color:#1e3a5f;">Jurisprudencia aplicavel (${data.jurisprudencias.length}):</div>`;
    for (const j of data.jurisprudencias) {
      html += `<div style="font-size:10px;color:#1e3a5f;margin-top:3px;padding:4px 8px;background:#e0e7ff;border-radius:4px;">`;
      html += `<strong>${j.numero}</strong> (${j.tribunal})`;
      if (j.url) html += ` <a href="${j.url}" target="_blank" style="color:#2563eb;">[link]</a>`;
      html += `<br><span style="color:#374151;">${j.ementa.substring(0, 180)}${j.ementa.length > 180 ? '...' : ''}</span>`;
      html += `</div>`;
    }
    html += `</div>`;
  }

  if (data.avisos?.length) {
    html += `<div style="font-size:10px;color:#92400e;margin-top:6px;">${data.avisos.join(' · ')}</div>`;
  }
  html += `</div>`;
  return html;
}

function renderizarDocComprobatorio(data) {
  let html = `<div style="text-align:left;">`;
  html += `<div style="font-size:14px;font-weight:700;color:#7c3aed;margin-bottom:6px;">🔬 ${data.tipo_documento}${data.via_ocr ? ' (via OCR)' : ''}</div>`;

  if (data.empresa) html += `<div style="font-size:11px;"><strong>Empresa:</strong> ${data.empresa}</div>`;
  if (data.cnpj) html += `<div style="font-size:10px;color:#6b7280;">CNPJ: ${data.cnpj}</div>`;

  if (data.agentes_encontrados?.length) {
    html += `<div style="margin-top:6px;background:#fef2f2;padding:6px 10px;border-radius:6px;border-left:3px solid #dc2626;">`;
    html += `<div style="font-size:12px;font-weight:700;color:#991b1b;">Agentes nocivos mencionados:</div>`;
    html += `<div style="font-size:11px;color:#374151;">${data.agentes_encontrados.map(a => a.replace(/_/g,' ')).join(', ')}</div>`;
    if (data.intensidades?.length) {
      html += `<div style="font-size:10px;margin-top:2px;">Intensidades: ${data.intensidades.join(', ')}</div>`;
    }
    html += `</div>`;
  } else {
    html += `<div style="font-size:11px;color:#6b7280;margin-top:4px;">Nenhum agente nocivo especifico detectado no texto</div>`;
  }

  if (data.jurisprudencias?.length) {
    html += `<div style="margin-top:6px;">`;
    html += `<div style="font-size:11px;font-weight:700;color:#1e3a5f;">Jurisprudencia (${data.jurisprudencias.length}):</div>`;
    for (const j of data.jurisprudencias.slice(0, 3)) {
      html += `<div style="font-size:10px;color:#1e3a5f;margin-top:2px;padding:3px 8px;background:#e0e7ff;border-radius:4px;">`;
      html += `<strong>${j.numero}</strong> (${j.tribunal})`;
      html += `</div>`;
    }
    html += `</div>`;
  }

  if (data.avisos?.length) {
    html += `<div style="font-size:10px;color:#92400e;margin-top:4px;">${data.avisos.join(' · ')}</div>`;
  }
  html += `</div>`;
  return html;
}

// ── Segurado ──────────────────────────────────────────────────────────────
function preencherFormularioSegurado(seg) {
  const dp = seg.dados_pessoais;
  document.getElementById('seg-nome').value = dp.nome || '';
  document.getElementById('seg-cpf').value = fmtCPF(dp.cpf || '');
  document.getElementById('seg-dn').value = dp.data_nascimento || '';
  document.getElementById('seg-sexo').value = dp.sexo || 'MASCULINO';
  document.getElementById('seg-nit').value = dp.nit || '';
}

function coletarSegurado() {
  return {
    dados_pessoais: {
      nome: document.getElementById('seg-nome').value.trim(),
      data_nascimento: document.getElementById('seg-dn').value.trim(),
      sexo: document.getElementById('seg-sexo').value,
      cpf: document.getElementById('seg-cpf').value.replace(/\D/g, '') || null,
      nit: document.getElementById('seg-nit').value.replace(/\D/g, '') || null,
    },
    vinculos: state.vinculos,
    beneficios_anteriores: state.beneficiosAnteriores || [],
  };
}

// ── Vínculos ──────────────────────────────────────────────────────────────
function renderizarVinculos() {
  const container = document.getElementById('vinculos-list');
  if (!state.vinculos.length) {
    container.innerHTML = '<p class="empty-state">Nenhum vínculo. Importe o CNIS ou adicione manualmente.</p>';
    return;
  }
  container.innerHTML = state.vinculos.map((v, i) => `
    <div class="vinculo-row">
      <div class="vinculo-info">
        <div class="vinculo-nome">${v.empregador_nome || v.empregador_cnpj || '(sem nome)'}</div>
        <div class="vinculo-periodo">${v.data_inicio} — ${v.data_fim || 'presente'} · ${tipoLabel(v.tipo_vinculo)}</div>
        <div class="vinculo-contrib">${v.contribuicoes?.length || 0} competência(s)</div>
      </div>
      <div class="vinculo-actions">
        <button class="btn btn-sm btn-secondary" onclick="editarVinculo(${i})">✏️</button>
        <button class="btn btn-sm btn-danger" onclick="removerVinculo(${i})">🗑️</button>
      </div>
    </div>`).join('');
}

function tipoLabel(t) {
  return { EMPREGADO:'CLT', EMPREGADO_DOMESTICO:'Doméstico', CONTRIBUINTE_INDIVIDUAL:'Individual',
    MEI:'MEI', FACULTATIVO:'Facultativo', TRABALHADOR_AVULSO:'Avulso', SEGURADO_ESPECIAL:'Rural' }[t] || t;
}

window.editarVinculo = i => {
  state.editandoVinculoIdx = i;
  const v = state.vinculos[i];
  document.getElementById('v-nome').value = v.empregador_nome || '';
  document.getElementById('v-cnpj').value = v.empregador_cnpj ? fmtCNPJ(v.empregador_cnpj) : '';
  document.getElementById('v-inicio').value = v.data_inicio || '';
  document.getElementById('v-fim').value = v.data_fim || '';
  document.getElementById('v-tipo').value = v.tipo_vinculo || 'EMPREGADO';
  document.getElementById('v-atividade').value = v.tipo_atividade || 'NORMAL';
  state.contribEditando = (v.contribuicoes || []).map(c => ({...c}));
  renderizarContribs();
  document.getElementById('modal-vinculo').classList.remove('hidden');
};

window.removerVinculo = i => {
  if (confirm('Remover este vínculo?')) { state.vinculos.splice(i,1); renderizarVinculos(); salvarNoLocalStorage(); }
};

document.getElementById('btn-add-vinculo').addEventListener('click', () => {
  state.editandoVinculoIdx = -1;
  ['v-nome','v-cnpj','v-inicio','v-fim'].forEach(id => document.getElementById(id).value = '');
  document.getElementById('v-tipo').value = 'EMPREGADO';
  document.getElementById('v-atividade').value = 'NORMAL';
  state.contribEditando = [];
  renderizarContribs();
  document.getElementById('modal-vinculo').classList.remove('hidden');
});

['btn-fechar-modal','btn-cancelar-modal'].forEach(id =>
  document.getElementById(id).addEventListener('click', fecharModal));
document.getElementById('modal-vinculo').addEventListener('click', e => {
  if (e.target === document.getElementById('modal-vinculo')) fecharModal();
});
function fecharModal() { document.getElementById('modal-vinculo').classList.add('hidden'); }

document.getElementById('btn-salvar-vinculo').addEventListener('click', () => {
  const vinculo = {
    empregador_nome: document.getElementById('v-nome').value.trim() || null,
    empregador_cnpj: document.getElementById('v-cnpj').value.replace(/\D/g,'') || null,
    data_inicio: document.getElementById('v-inicio').value.trim(),
    data_fim: document.getElementById('v-fim').value.trim() || null,
    tipo_vinculo: document.getElementById('v-tipo').value,
    tipo_atividade: document.getElementById('v-atividade').value,
    contribuicoes: [...state.contribEditando],
  };
  if (!vinculo.data_inicio) { toast('Data de início obrigatória','error'); return; }
  if (state.editandoVinculoIdx === -1) state.vinculos.push(vinculo);
  else state.vinculos[state.editandoVinculoIdx] = vinculo;
  renderizarVinculos();
  salvarNoLocalStorage();
  fecharModal();
  toast('Vínculo salvo','success');
});

document.getElementById('btn-add-contrib').addEventListener('click', () => {
  state.contribEditando.push({ competencia:'', salario:'', teto_aplicado:false });
  renderizarContribs();
});

function renderizarContribs() {
  const container = document.getElementById('contrib-list');
  if (!state.contribEditando.length) {
    container.innerHTML = '<p class="empty-state" style="padding:8px 0">Clique em "+ Competência" para adicionar.</p>';
    return;
  }
  container.innerHTML = state.contribEditando.map((c,i) => `
    <div class="contrib-row">
      <input type="text" placeholder="MM/AAAA" maxlength="7" value="${c.competencia}"
        oninput="state.contribEditando[${i}].competencia=this.value" />
      <input type="text" placeholder="Salário R$" value="${c.salario}"
        oninput="state.contribEditando[${i}].salario=this.value" />
      <button class="btn btn-sm btn-danger" onclick="removerContrib(${i})">✕</button>
    </div>`).join('');
}

window.removerContrib = i => { state.contribEditando.splice(i,1); renderizarContribs(); };

// ── Resumo do segurado ────────────────────────────────────────────────────
document.getElementById('btn-calcular-resumo').addEventListener('click', async () => {
  const seg = coletarSegurado();
  if (!seg.dados_pessoais.nome || !seg.dados_pessoais.data_nascimento) {
    toast('Preencha nome e data de nascimento','error'); return;
  }
  const der = new Date().toLocaleDateString('pt-BR');
  const btn = document.getElementById('btn-calcular-resumo');
  btn.disabled = true; btn.innerHTML = '<span class="loader"></span> Calculando...';
  try {
    const res = await fetch(`${API}/calculo/resumo`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ segurado: seg, der, tipo:'transicao' }),
    });
    const data = await res.json();
    if (!res.ok) { toast(data.detail||'Erro','error'); return; }
    renderizarResumo(data);
  } catch { toast('Erro de conexão','error'); }
  finally { btn.disabled=false; btn.textContent='📊 Ver Resumo'; }
});

function renderizarResumo(d) {
  const el = document.getElementById('resumo-segurado');
  const tc = d.tempo_contribuicao;
  el.innerHTML = `
    <h3 class="card-title">Resumo — ${d.nome}</h3>
    <div class="resumo-grid">
      <div class="resumo-item"><div class="resumo-label">Idade</div><div class="resumo-valor">${d.idade_na_der.toFixed(1)} anos</div></div>
      <div class="resumo-item"><div class="resumo-label">Tempo de Contribuição</div><div class="resumo-valor">${tc.anos}a ${tc.meses}m ${tc.dias}d</div><div class="resumo-detalhe">${tc.total_dias.toLocaleString('pt-BR')} dias</div></div>
      <div class="resumo-item"><div class="resumo-label">Carência</div><div class="resumo-valor">${d.carencia_meses} meses</div><div class="resumo-detalhe">exigido: 180</div></div>
      <div class="resumo-item"><div class="resumo-label">Vínculos</div><div class="resumo-valor">${d.num_vinculos}</div></div>
      <div class="resumo-item"><div class="resumo-label">SB Estimado</div><div class="resumo-valor text-verde">${d.salario_beneficio ? 'R$ '+fmtDecimal(d.salario_beneficio) : '—'}</div></div>
      <div class="resumo-item"><div class="resumo-label">Teto Vigente</div><div class="resumo-valor">R$ ${fmtDecimal(d.teto_vigente)}</div></div>
    </div>`;
  el.classList.remove('hidden');
}

// ── Cálculo de benefício ──────────────────────────────────────────────────
document.getElementById('calc-tipo').addEventListener('change', function() {
  const isPensao = this.value === 'pensao';
  document.getElementById('grupo-pensao').classList.toggle('hidden', !isPensao);
  document.getElementById('grupo-dependentes').classList.toggle('hidden', !isPensao);
});

document.getElementById('btn-calcular').addEventListener('click', async () => {
  const seg = coletarSegurado();
  if (!seg.dados_pessoais.nome) { toast('Preencha os dados do segurado primeiro','error'); return; }
  const tipo = document.getElementById('calc-tipo').value;
  const der = document.getElementById('calc-der').value.trim();
  if (!der) { toast('Informe a DER','error'); return; }

  const btn = document.getElementById('btn-calcular');
  btn.disabled = true; btn.innerHTML = '<span class="loader"></span> Calculando...';
  const resultEl = document.getElementById('resultado-calculo');
  resultEl.innerHTML = ''; resultEl.classList.add('hidden');

  try {
    let url, body;
    if (tipo === 'pensao') {
      const obito = document.getElementById('calc-obito').value.trim();
      if (!obito) { toast('Informe a data do óbito','error'); return; }
      url = `${API}/calculo/pensao-morte`;
      body = { segurado:seg, der, num_dependentes:parseInt(document.getElementById('calc-dependentes').value)||1, data_obito:obito };
    } else if (tipo === 'auxilio_doenca') { url=`${API}/calculo/auxilio-doenca`; body={segurado:seg,der,acidentario:false};
    } else if (tipo === 'auxilio_acidente') { url=`${API}/calculo/auxilio-doenca`; body={segurado:seg,der,acidentario:true};
    } else if (tipo === 'invalidez') { url=`${API}/calculo/invalidez`; body={segurado:seg,der,acidentaria:false};
    } else if (tipo === 'invalidez_acidentaria') { url=`${API}/calculo/invalidez`; body={segurado:seg,der,acidentaria:true};
    } else { url=`${API}/calculo/aposentadoria`; body={segurado:seg,der,tipo}; }

    const res = await fetch(url, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) });
    const data = await res.json();
    if (!res.ok) { toast(data.detail||'Erro no cálculo','error'); return; }
    state.ultimoCalculo = data;
    salvarNoLocalStorage();
    renderizarResultado(data, resultEl);
    resultEl.classList.remove('hidden');
  } catch { toast('Erro de conexão com o servidor','error'); }
  finally { btn.disabled=false; btn.textContent='⚡ Calcular'; }
});

function renderizarResultado(data, container) {
  const cls = data.elegivel ? 'elegivel' : 'inelegivel';
  const emoji = data.elegivel ? '✅' : '❌';
  const titulo = data.elegivel ? (data.melhor_cenario?.nome_regra||'Elegível') : 'Não elegível — veja os cenários abaixo';

  let html = `<div class="card" style="padding:0;overflow:hidden;">
    <div class="resultado-header ${cls}">
      <div>
        <div style="font-size:13px;opacity:.85;">${emoji} ${titulo}</div>
        <div class="resultado-rmi">${data.elegivel ? 'R$ '+fmtDecimal(data.rmi) : '—'}</div>
        <div class="resultado-label">Renda Mensal Inicial (RMI)</div>
      </div>
    </div>
    <div style="padding:20px;">
      <h4 style="margin-bottom:12px;">Comparativo de Todos os Cenários</h4>
      <div class="cenario-list">`;

  (data.todos_cenarios||[]).forEach((c,i) => {
    const badge = c.elegivel ? '<span class="badge badge-ok">Elegível</span>' : '<span class="badge badge-no">Não elegível</span>';
    const rmiTxt = c.elegivel ? `R$ ${fmtDecimal(c.rmi)}` : (c.faltam_dias>0 ? `Faltam ${c.faltam_dias.toLocaleString('pt-BR')} dias` : '—');
    html += `<div class="cenario-item ${c.elegivel?'':'cenario-inelegivel'}">
      <div class="cenario-header" onclick="toggleCenario(${i})">
        <span class="cenario-nome">${c.nome_regra}</span>
        <span style="display:flex;gap:10px;align-items:center;">${badge}<span class="cenario-rmi">${rmiTxt}</span><span>▼</span></span>
      </div>
      <div class="cenario-body" id="cenario-${i}">
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;margin-bottom:12px;">
          <div><span style="font-size:11px;color:#9ca3af">BASE LEGAL</span><br>${c.base_legal}</div>
          <div><span style="font-size:11px;color:#9ca3af">SB</span><br>R$ ${fmtDecimal(c.salario_beneficio)}</div>
          <div><span style="font-size:11px;color:#9ca3af">COEFICIENTE</span><br>${(parseFloat(c.coeficiente)*100).toFixed(2)}%</div>
          ${c.fator_previdenciario ? `<div><span style="font-size:11px;color:#9ca3af">FATOR PREV.</span><br>${parseFloat(c.fator_previdenciario).toFixed(4)}</div>` : ''}
          ${c.tempo_contribuicao ? `<div><span style="font-size:11px;color:#9ca3af">TC</span><br>${c.tempo_contribuicao.anos}a ${c.tempo_contribuicao.meses}m ${c.tempo_contribuicao.dias}d</div>` : ''}
        </div>
        ${c.memoria?.length ? renderMemoria(c.memoria) : ''}
        ${c.avisos?.length ? `<div class="alert alert-warning" style="margin-top:8px;">${c.avisos.join('<br>')}</div>` : ''}
      </div>
    </div>`;
  });
  html += `</div></div></div>`;
  container.innerHTML = html;
}

function renderMemoria(itens) {
  if (!itens?.length) return '';
  const rows = itens.map(item => {
    const pad = '&nbsp;'.repeat((item.nivel||0)*4);
    const fund = item.fundamentacao ? `<small style="color:#6b7280">${item.fundamentacao.norma} ${item.fundamentacao.artigo}</small>` : '';
    return `<tr><td>${pad}${item.descricao||''}${fund?'<br>'+fund:''}</td><td style="text-align:right;font-weight:${item.valor?'600':'normal'}">${item.valor??''}</td></tr>`;
  }).join('');
  return `<table class="memoria-table"><thead><tr><th>Etapa</th><th style="text-align:right">Valor</th></tr></thead><tbody>${rows}</tbody></table>`;
}

window.toggleCenario = i => document.getElementById(`cenario-${i}`)?.classList.toggle('open');

// ── MODO PLANEJAMENTO: Detecção inteligente de cenário ────────────────────
function configurarModoPlanejamento() {
  if (!state.beneficiosCNIS?.length) return;
  const especiesApos = [41,42,46,57,99];
  const ativos = state.beneficiosCNIS.filter(b => b.situacao === 'ATIVO' && especiesApos.includes(Number(b.especie_codigo)));
  const indeferidos = state.beneficiosCNIS.filter(b => b.situacao === 'INDEFERIDO');

  if (ativos.length) {
    const b = ativos[0];
    state.modoCalculo = 'REVISAO';
    state.aposentadoriaAtiva = b;
    if (b.data_inicio) {
      const planDer = document.getElementById('plan-der');
      if (planDer) planDer.value = b.data_inicio;
      const derOrigGroup = document.getElementById('plan-der-original-group');
      const derOrigInput = document.getElementById('plan-der-original');
      if (derOrigGroup && derOrigInput) { derOrigInput.value = b.data_inicio; derOrigGroup.style.display = ''; }
      const derLabel = document.getElementById('plan-der-label');
      if (derLabel) derLabel.textContent = 'DER para Cálculo *';
      const derHint = document.getElementById('plan-der-hint');
      if (derHint) { derHint.style.display = 'block'; derHint.textContent = 'Pré-preenchido com a DER da aposentadoria. Para reafirmação (Tema 995 STJ), altere para a data desejada.'; }
      ['teto-dib','at-dib'].forEach(id => { const el=document.getElementById(id); if(el&&!el.value) el.value=b.data_inicio; });
      ['teto-der','pcd-der'].forEach(id => { const el=document.getElementById(id); if(el&&!el.value) el.value=b.data_inicio; });
    }
    document.getElementById('plan-titulo').textContent = 'Revisão de Aposentadoria';
    document.getElementById('plan-subtitulo').textContent = 'Segurado já aposentado. O sistema recalcula na DER original para verificar se o INSS concedeu o melhor benefício.';
    const alertaEl = document.getElementById('plan-modo-alerta');
    alertaEl.className = 'card';
    alertaEl.style.cssText = 'border:3px solid #dc2626;background:#fef2f2;padding:16px;margin-bottom:16px;';
    alertaEl.innerHTML = `<div style="display:flex;align-items:center;gap:12px;">
      <div style="font-size:32px;">🔍</div><div>
        <div style="font-size:15px;font-weight:800;color:#991b1b;">MODO REVISÃO — Segurado já aposentado</div>
        <div style="font-size:13px;color:#7f1d1d;margin-top:4px;"><strong>${b.especie||'Aposentadoria'}</strong> (espécie ${b.especie_codigo}) concedida em <strong>${b.data_inicio}</strong>${b.rmi ? ` — RMI: <strong>R$ ${b.rmi}</strong>` : ''}</div>
        <div style="font-size:12px;color:#374151;margin-top:6px;">O sistema vai recalcular a RMI na DER original por TODAS as regras e comparar com o que o INSS concedeu.</div>
        <div style="font-size:11px;color:#6b7280;margin-top:4px;">Art. 687, IN PRES/INSS 128/2022 — Princípio do Melhor Benefício (STF Tema 334)</div>
      </div></div>`;
  } else if (indeferidos.length) {
    const b = indeferidos[0];
    state.modoCalculo = 'INDEFERIDO';
    state.beneficioIndeferido = b;
    if (b.data_inicio) {
      const planDer = document.getElementById('plan-der');
      if (planDer) planDer.value = b.data_inicio;
      const derOrigGroup = document.getElementById('plan-der-original-group');
      const derOrigInput = document.getElementById('plan-der-original');
      if (derOrigGroup && derOrigInput) { derOrigInput.value = b.data_inicio; derOrigGroup.style.display = ''; }
      const derLabel = document.getElementById('plan-der-label');
      if (derLabel) derLabel.textContent = 'DER do Pedido Negado *';
      const derHint = document.getElementById('plan-der-hint');
      if (derHint) { derHint.style.display = 'block'; derHint.textContent = 'Data do requerimento indeferido. Para reafirmação da DER (Tema 995 STJ), altere para data posterior.'; }
    }
    document.getElementById('plan-titulo').textContent = 'Análise de Benefício Indeferido';
    document.getElementById('plan-subtitulo').textContent = 'Benefício negado pelo INSS. O sistema verifica se o segurado tinha direito na DER e calcula os atrasados.';
    const alertaEl = document.getElementById('plan-modo-alerta');
    alertaEl.className = 'card';
    alertaEl.style.cssText = 'border:3px solid #f59e0b;background:#fffbeb;padding:16px;margin-bottom:16px;';
    alertaEl.innerHTML = `<div style="display:flex;align-items:center;gap:12px;">
      <div style="font-size:32px;">⚠️</div><div>
        <div style="font-size:15px;font-weight:800;color:#92400e;">BENEFÍCIO INDEFERIDO — Verificar direito na DER</div>
        <div style="font-size:13px;color:#78350f;margin-top:4px;"><strong>${b.especie||'Benefício'}</strong> indeferido em <strong>${b.data_inicio||'?'}</strong></div>
        <div style="font-size:12px;color:#374151;margin-top:6px;">O sistema calcula se o segurado preenchia os requisitos na DER do pedido negado. Se não, busca a data mais próxima (Reafirmação — Tema 995 STJ).</div>
      </div></div>`;
  }
}

function resetarModoPlanejamento() {
  document.getElementById('plan-titulo').textContent = 'Planejamento Previdenciário';
  document.getElementById('plan-subtitulo').textContent = 'Descubra quando você poderá se aposentar por cada regra e qual é a melhor estratégia.';
  const alertaEl = document.getElementById('plan-modo-alerta');
  alertaEl.className = 'hidden'; alertaEl.innerHTML = '';
  const derOrigGroup = document.getElementById('plan-der-original-group');
  if (derOrigGroup) derOrigGroup.style.display = 'none';
  const derLabel = document.getElementById('plan-der-label');
  if (derLabel) derLabel.textContent = 'Data de Referência *';
  const derHint = document.getElementById('plan-der-hint');
  if (derHint) { derHint.style.display = 'none'; derHint.textContent = ''; }
  const planDer = document.getElementById('plan-der');
  if (planDer) { const h=new Date(); planDer.value=`${String(h.getDate()).padStart(2,'0')}/${String(h.getMonth()+1).padStart(2,'0')}/${h.getFullYear()}`; }
}

// ── PAINEL DE BENEFÍCIO ATIVO (fixo no topo do planejamento) ─────────────
// ── RENDERIZAR ANÁLISE ESPECIAL DE VÍNCULOS (CTPS/CNIS) ─────────────────
function renderizarAnaliseVinculos(vinculos, nome, cpf, pis, avisos, origem) {
  const corProb = { ALTA:'#dc2626', MEDIA:'#d97706', BAIXA:'#2563eb', NENHUMA:'#6b7280' };
  const bgProb = { ALTA:'#fef2f2', MEDIA:'#fffbeb', BAIXA:'#eff6ff', NENHUMA:'#f9fafb' };
  const labelProb = { ALTA:'ALTA PROBABILIDADE', MEDIA:'MEDIA PROBABILIDADE', BAIXA:'BAIXA PROBABILIDADE', NENHUMA:'SEM INDICATIVO' };

  let html = `<div style="text-align:left;max-height:500px;overflow-y:auto;">`;

  // Cabeçalho
  if (nome || cpf) {
    html += `<div style="font-size:14px;font-weight:700;margin-bottom:6px;">✅ ${nome || origem}${cpf ? ` — CPF: ${cpf}` : ''}${pis ? ` | PIS: ${pis}` : ''}</div>`;
  }
  html += `<div style="font-size:12px;font-weight:700;color:#1e40af;margin-bottom:8px;border-bottom:2px solid #3b82f6;padding-bottom:4px;">Analise de Atividade Especial — ${vinculos.length} vinculo(s)</div>`;

  for (const v of vinculos) {
    const esp = v.especial || {};
    const prob = esp.probabilidade || 'NENHUMA';
    const borderColor = esp.possivel ? corProb[prob] : '#e5e7eb';

    html += `<div style="border-left:4px solid ${borderColor};background:${bgProb[prob]};padding:8px 12px;margin-bottom:8px;border-radius:0 8px 8px 0;">`;

    // Empresa + periodo
    html += `<div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:4px;">`;
    html += `<div style="font-weight:700;font-size:13px;color:#111827;">${v.empregador_nome || '(sem nome)'}</div>`;
    html += `<div style="font-size:10px;color:#6b7280;">${v.data_inicio || '?'} — ${v.data_fim || 'atual'}</div>`;
    html += `</div>`;

    // CNPJ
    if (v.empregador_cnpj) {
      html += `<div style="font-size:10px;color:#9ca3af;">CNPJ: ${v.empregador_cnpj}</div>`;
    }

    // Cargo + CBO
    if (v.cargo || v.cbo) {
      html += `<div style="font-size:11px;margin-top:3px;">`;
      if (v.cargo) html += `<strong>Cargo:</strong> ${v.cargo}`;
      if (v.cbo) html += ` | <strong>CBO:</strong> ${v.cbo}`;
      html += `</div>`;
    }

    // CBO Info + NRs
    if (v.cbo_info) {
      html += `<div style="font-size:10px;color:#4338ca;margin-top:2px;">${v.cbo_info}</div>`;
    }
    if (v.cbo_nr?.length) {
      html += `<div style="font-size:10px;color:#7c3aed;margin-top:2px;">NRs: ${v.cbo_nr.join(', ')}</div>`;
    }

    // Análise especial
    if (esp.possivel) {
      html += `<div style="margin-top:6px;padding:6px 10px;background:${prob==='ALTA'?'#fecaca':prob==='MEDIA'?'#fde68a':'#bfdbfe'};border-radius:6px;">`;
      html += `<div style="font-size:12px;font-weight:800;color:${corProb[prob]};">${labelProb[prob]} — Especial ${esp.anos || 25} anos</div>`;
      html += `<div style="font-size:10px;color:#374151;margin-top:2px;"><strong>Detectado via:</strong> ${esp.via === 'empregador' ? 'nome da empresa' : esp.via === 'cargo' ? 'cargo/funcao' : 'codigo CBO'}</div>`;
      if (esp.agentes?.length) {
        html += `<div style="font-size:10px;color:#374151;margin-top:2px;"><strong>Agentes nocivos:</strong> ${esp.agentes.join(', ')}</div>`;
      }
      if (esp.fundamentacao) {
        html += `<div style="font-size:10px;color:#374151;margin-top:2px;"><strong>Fundamentacao:</strong> ${esp.fundamentacao}</div>`;
      }
      if (esp.recomendacao) {
        html += `<div style="font-size:10px;color:#065f46;margin-top:2px;font-style:italic;">${esp.recomendacao}</div>`;
      }
      html += `</div>`;

      // Jurisprudências
      if (v.jurisprudencias?.length) {
        html += `<div style="margin-top:6px;">`;
        html += `<div style="font-size:11px;font-weight:700;color:#1e3a5f;">Jurisprudencia aplicavel (${v.jurisprudencias.length}):</div>`;
        for (const j of v.jurisprudencias) {
          html += `<div style="font-size:10px;color:#1e3a5f;margin-top:3px;padding:4px 8px;background:#e0e7ff;border-radius:4px;">`;
          html += `<strong>${j.numero}</strong> (${j.tribunal})`;
          if (j.url) html += ` <a href="${j.url}" target="_blank" style="color:#2563eb;">[link]</a>`;
          html += `<br><span style="color:#374151;">${j.ementa.substring(0, 200)}${j.ementa.length > 200 ? '...' : ''}</span>`;
          if (j.aplicabilidade) html += `<br><span style="color:#065f46;font-style:italic;">→ ${j.aplicabilidade.substring(0, 150)}${j.aplicabilidade.length > 150 ? '...' : ''}</span>`;
          html += `</div>`;
        }
        html += `</div>`;
      }
    } else {
      html += `<div style="font-size:10px;color:#9ca3af;margin-top:4px;">Sem indicativo de atividade especial detectado</div>`;
    }

    html += `</div>`;
  }

  if (avisos?.length) {
    html += `<div style="font-size:10px;color:#92400e;margin-top:4px;">${avisos.slice(0,3).join(' · ')}</div>`;
  }
  html += `</div>`;
  return html;
}

function atualizarSugestoesDER() {
  const box = document.getElementById('calc-der-sugestoes');
  if (!box) return;
  const datas = [];

  // Aposentadoria ativa — DER original
  if (state.aposentadoriaAtiva?.data_inicio) {
    datas.push({
      data: state.aposentadoriaAtiva.data_inicio,
      motivo: `DER da aposentadoria (${state.aposentadoriaAtiva.especie || 'Esp. ' + state.aposentadoriaAtiva.especie_codigo})`,
      tipo: 'revisao',
    });
  }

  // Beneficio indeferido
  if (state.beneficioIndeferido?.data_inicio) {
    datas.push({
      data: state.beneficioIndeferido.data_inicio,
      motivo: `DER do pedido indeferido (${state.beneficioIndeferido.especie || ''})`,
      tipo: 'indeferido',
    });
  }

  // Outros beneficios do CNIS com data
  if (state.beneficiosCNIS?.length) {
    for (const b of state.beneficiosCNIS) {
      if (b.data_inicio && !datas.find(d => d.data === b.data_inicio)) {
        datas.push({
          data: b.data_inicio,
          motivo: `${b.especie || 'Beneficio'} (${b.situacao || ''})`,
          tipo: b.situacao === 'ATIVO' ? 'revisao' : b.situacao === 'INDEFERIDO' ? 'indeferido' : 'outro',
        });
      }
    }
  }

  if (!datas.length) {
    box.classList.add('hidden');
    return;
  }

  // Auto-preencher com a data mais relevante (aposentadoria > indeferido > outro)
  const calcDer = document.getElementById('calc-der');
  const hoje = new Date().toLocaleDateString('pt-BR');
  if (calcDer && (!calcDer.value || calcDer.value === hoje)) {
    const melhor = datas.find(d => d.tipo === 'revisao') || datas.find(d => d.tipo === 'indeferido') || datas[0];
    if (melhor) calcDer.value = melhor.data;
  }

  box.classList.remove('hidden');
  box.innerHTML = `
    <div style="font-weight:700;margin-bottom:4px;">Datas detectadas no CNIS:</div>
    ${datas.map(d => `
      <div style="display:flex;align-items:center;gap:8px;margin-top:3px;">
        <span style="background:${d.tipo === 'revisao' ? '#dcfce7;color:#166534' : d.tipo === 'indeferido' ? '#fef3c7;color:#92400e' : '#e0e7ff;color:#3730a3'};padding:1px 8px;border-radius:4px;font-weight:700;cursor:pointer;font-size:11px;"
              onclick="document.getElementById('calc-der').value='${d.data}'">${d.data}</span>
        <span>${d.motivo}</span>
      </div>
    `).join('')}
    <div style="margin-top:6px;font-size:10px;color:#6b7280;">Clique em uma data para usar como DER do calculo.</div>`;
}

function atualizarPainelBeneficioAtivo(beneficio) {
  const painel = document.getElementById('plan-beneficio-ativo');
  if (!painel || !beneficio) { if(painel) painel.classList.add('hidden'); return; }
  const rmi = beneficio.rmi || state.rmiCarta || null;
  const nb = beneficio.nb || beneficio.numero_beneficio || '';
  painel.classList.remove('hidden');
  painel.innerHTML = `
    <div>
      <div style="font-size:11px;opacity:0.8;">BENEFÍCIO ATIVO DETECTADO</div>
      <div style="font-size:18px;font-weight:800;margin-top:2px;">${beneficio.especie || ''} (Esp. ${beneficio.especie_codigo || ''})</div>
      ${nb ? `<div style="font-size:12px;opacity:0.9;">NB: ${nb}</div>` : ''}
    </div>
    <div style="text-align:center;">
      <div style="font-size:11px;opacity:0.8;">DIB / DER</div>
      <div style="font-size:18px;font-weight:800;">${beneficio.data_inicio || '—'}</div>
    </div>
    <div style="text-align:right;">
      <div style="font-size:11px;opacity:0.8;">RMI CONCEDIDA</div>
      <div style="font-size:22px;font-weight:900;">${rmi ? 'R$ ' + fmtDecimal(rmi) : 'Importe a Carta de Concessão'}</div>
      ${!rmi ? '<div style="font-size:10px;opacity:0.7;">ou o valor aparecerá do CNIS</div>' : ''}
    </div>`;
}

// ── APLICAR FATOR ESPECIAL E RECALCULAR ──────────────────────────────────
window.aplicarFatorEspecial = async function(vinculoIdx, tipoAtividade) {
  if (vinculoIdx < 0 || vinculoIdx >= state.vinculos.length) return;
  const oldTipo = state.vinculos[vinculoIdx].tipo_atividade;
  state.vinculos[vinculoIdx].tipo_atividade = tipoAtividade;
  salvarNoLocalStorage();
  renderizarVinculos();
  const nomeEmp = state.vinculos[vinculoIdx].empregador_nome || 'Vínculo';
  const label = tipoAtividade === 'NORMAL' ? 'Normal' : tipoAtividade.replace('ESPECIAL_', 'Especial ') + ' anos';
  toast(`${nomeEmp} alterado para ${label}. Recalculando...`, 'info');
  // Recalcular planejamento automaticamente
  document.getElementById('btn-planejar')?.click();
};

// ── PLANEJAMENTO PREVIDENCIÁRIO ───────────────────────────────────────────
document.getElementById('btn-planejar').addEventListener('click', async () => {
  const seg = coletarSegurado();
  if (!seg.dados_pessoais.nome || !seg.dados_pessoais.data_nascimento) {
    toast('Preencha os dados do segurado primeiro','error'); return;
  }
  const der = document.getElementById('plan-der').value.trim();
  if (!der) { toast('Informe a data de referência','error'); return; }
  const salStr = document.getElementById('plan-salario').value.trim().replace(/\./g,'').replace(',','.');

  const btn = document.getElementById('btn-planejar');
  btn.disabled = true; btn.innerHTML = '<span class="loader"></span> Calculando projeções...';
  const resultEl = document.getElementById('resultado-planejamento');

  try {
    const res = await fetch(`${API}/planejamento/projecao`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ segurado:seg, der, salario_projetado: salStr||null, beneficios: state.beneficiosCNIS || null }),
    });
    const data = await res.json();
    if (!res.ok) { toast(data.detail||'Erro','error'); return; }
    state.ultimoPlanejamento = data;
    renderizarPlanejamento(data, resultEl);
    resultEl.classList.remove('hidden');
  } catch (e) { toast('Erro de conexão: '+e.message,'error'); }
  finally { btn.disabled=false; btn.textContent='📅 Calcular Planejamento'; }
});

function renderizarPlanejamento(data, container) {
  const nome = coletarSegurado().dados_pessoais.nome.split(' ')[0] || 'Segurado';
  const tc = data.tc_atual;
  const sal = fmtDecimal(data.salario_projetado);
  const alcancaveis = (data.projecoes||[]).filter(p => p.data_elegibilidade).sort((a,b) => a.meses_faltantes - b.meses_faltantes);
  const melhor = alcancaveis[0];

  // ── Barra de progresso de TC ──────────────────────────────────────────────
  const tcTotalMeses = tc.anos * 12 + tc.meses;
  const meta = 420;
  const pct = Math.min(100, Math.round(tcTotalMeses / meta * 100));

  // ── Regime aplicado e Alertas Antialucinacao ──────────────────────────────
  let htmlAlertas = '';
  const regime = data.regime_aplicado || '';
  if (regime) {
    const regimeLabel = regime === 'PRE_REFORMA'
      ? 'Regime PRE-REFORMA (Lei 8.213/91 + Lei 9.876/99)'
      : 'Regime POS-REFORMA (EC 103/2019)';
    const regimeCor = regime === 'PRE_REFORMA' ? '#92400e' : '#1e40af';
    htmlAlertas += `<div style="background:${regime==='PRE_REFORMA'?'#fef3c7':'#eff6ff'};border-left:4px solid ${regimeCor};padding:10px 14px;border-radius:6px;margin-bottom:12px;font-size:12px;color:${regimeCor};"><strong>Regime Juridico:</strong> ${regimeLabel}</div>`;
  }

  const validacao = data.validacao || {};
  if (validacao.fatais > 0 || validacao.altos > 0) {
    htmlAlertas += `<div style="background:#fef2f2;border-left:4px solid #dc2626;padding:12px 14px;border-radius:6px;margin-bottom:12px;">
      <div style="font-weight:700;font-size:13px;color:#991b1b;">ALERTAS DE VALIDACAO</div>
      <div style="font-size:12px;color:#7f1d1d;margin-top:4px;">${validacao.mensagem_confiabilidade||''}</div>`;
    const alertas = data.alertas_antialucinacao || [];
    alertas.forEach(a => {
      const corGrav = a.gravidade === 'FATAL' ? '#dc2626' : a.gravidade === 'ALTA' ? '#ea580c' : '#ca8a04';
      htmlAlertas += `<div style="margin-top:6px;padding:6px 8px;background:#fff;border-radius:4px;border:1px solid ${corGrav}33;font-size:11px;">
        <span style="color:${corGrav};font-weight:700;">[${a.gravidade}]</span> ${a.mensagem}
        ${a.base_legal ? `<br><em style="color:#6b7280;">Base legal: ${a.base_legal}</em>` : ''}
      </div>`;
    });
    htmlAlertas += `</div>`;
  } else if (validacao.confiavel) {
    htmlAlertas += `<div style="background:#f0fdf4;border-left:4px solid #16a34a;padding:8px 14px;border-radius:6px;margin-bottom:12px;font-size:12px;color:#166534;">Calculo validado — nenhum alerta fatal detectado.</div>`;
  }

  // ── Classificação FATO / PROJEÇÃO / TESE ───────────────────────────────────
  if (data.classificacao_dados) {
    const cd = data.classificacao_dados;
    htmlAlertas += `<div class="card" style="border:2px solid #1d4ed8;margin-bottom:16px;position:relative;overflow:hidden;">
      <div style="position:absolute;top:0;right:0;background:#1d4ed8;color:#fff;padding:4px 12px;border-radius:0 0 0 8px;font-size:10px;font-weight:700;letter-spacing:1px;">TRANSPARÊNCIA</div>
      <h3 class="card-title" style="margin-bottom:4px;">📋 Classificação dos Dados: FATO · PROJEÇÃO · TESE</h3>
      <p style="font-size:11px;color:#6b7280;margin-bottom:14px;">${cd.disclaimer_geral || ''}</p>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px;">`;

    // FATOS
    if (cd.fatos?.length) {
      htmlAlertas += `<div style="background:#f0fdf4;border-radius:10px;padding:14px;border-left:4px solid #16a34a;">
        <div style="font-size:12px;font-weight:800;color:#065f46;margin-bottom:10px;letter-spacing:0.5px;">📌 FATOS — Dados Documentais</div>`;
      cd.fatos.forEach(f => {
        if (!f.valor || f.valor === '?') return;
        const confCor = f.confianca === 'ALTA' ? '#065f46' : f.confianca === 'MEDIA' ? '#b45309' : '#991b1b';
        htmlAlertas += `<div style="margin-bottom:8px;padding:6px 8px;background:#fff;border-radius:6px;border:1px solid #dcfce7;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span style="font-size:12px;font-weight:600;color:#374151;">${f.descricao}</span>
            <span style="font-size:10px;color:${confCor};font-weight:700;background:${confCor}15;padding:1px 6px;border-radius:3px;">${f.confianca}</span>
          </div>
          <div style="font-size:13px;font-weight:700;color:#065f46;margin-top:2px;">${f.valor}</div>
          ${f.fonte ? `<div style="font-size:10px;color:#9ca3af;margin-top:2px;">Fonte: ${f.fonte}</div>` : ''}
        </div>`;
      });
      htmlAlertas += `</div>`;
    }

    // PROJEÇÕES
    if (cd.projecoes?.length) {
      htmlAlertas += `<div style="background:#eff6ff;border-radius:10px;padding:14px;border-left:4px solid #2563eb;">
        <div style="font-size:12px;font-weight:800;color:#1e40af;margin-bottom:10px;letter-spacing:0.5px;">📊 PROJEÇÕES — Estimativas Futuras</div>`;
      cd.projecoes.forEach(p => {
        const confCor = p.confianca === 'ALTA' ? '#065f46' : p.confianca === 'MEDIA' ? '#b45309' : '#991b1b';
        htmlAlertas += `<div style="margin-bottom:8px;padding:6px 8px;background:#fff;border-radius:6px;border:1px solid #dbeafe;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span style="font-size:12px;font-weight:600;color:#374151;">${p.descricao}</span>
            <span style="font-size:10px;color:${confCor};font-weight:700;background:${confCor}15;padding:1px 6px;border-radius:3px;">${p.confianca}</span>
          </div>
          <div style="font-size:13px;font-weight:700;color:#1e40af;margin-top:2px;">${p.valor}</div>
          ${p.disclaimer ? `<div style="font-size:10px;color:#9ca3af;margin-top:2px;font-style:italic;">⚠️ ${p.disclaimer}</div>` : ''}
        </div>`;
      });
      htmlAlertas += `</div>`;
    }

    // TESES
    if (cd.teses?.length) {
      htmlAlertas += `<div style="background:#faf5ff;border-radius:10px;padding:14px;border-left:4px solid #7c3aed;">
        <div style="font-size:12px;font-weight:800;color:#5b21b6;margin-bottom:10px;letter-spacing:0.5px;">⚖️ TESES — Argumentos Estratégicos</div>`;
      cd.teses.forEach(t => {
        const confCor = t.confianca === 'ALTA' ? '#065f46' : t.confianca === 'MEDIA' ? '#b45309' : '#991b1b';
        htmlAlertas += `<div style="margin-bottom:8px;padding:6px 8px;background:#fff;border-radius:6px;border:1px solid #ede9fe;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span style="font-size:12px;font-weight:600;color:#374151;">${t.descricao}</span>
            <span style="font-size:10px;color:${confCor};font-weight:700;background:${confCor}15;padding:1px 6px;border-radius:3px;">${t.confianca}</span>
          </div>
          <div style="font-size:13px;font-weight:700;color:#5b21b6;margin-top:2px;">${t.valor}</div>
          ${t.disclaimer ? `<div style="font-size:10px;color:#9ca3af;margin-top:2px;font-style:italic;">⚠️ ${t.disclaimer}</div>` : ''}
        </div>`;
      });
      htmlAlertas += `</div>`;
    }

    htmlAlertas += `</div></div>`;
  }

  // ── Hero: situacao atual ──────────────────────────────────────────────────
  let html = htmlAlertas + `
  <div class="plan-hero">
    <div class="plan-hero-left">
      <div class="plan-hero-nome">${nome}</div>
      <div class="plan-hero-status ${data.elegiveis_agora ? 'elegivel' : 'pendente'}">
        ${data.elegiveis_agora ? '✅ Já pode se aposentar' : '⏳ Ainda não elegível'}
      </div>
      ${melhor ? `<div class="plan-hero-proximo">Próxima aposentadoria: <strong>${melhor.data_elegibilidade}</strong> pela regra <em>${melhor.regra.split('—')[0].trim()}</em></div>` : ''}
    </div>
    <div class="plan-hero-right">
      <div class="plan-stat">
        <div class="plan-stat-val">${tc.anos}<span>anos</span></div>
        <div class="plan-stat-label">${tc.meses}m ${tc.dias}d de TC</div>
      </div>
      <div class="plan-stat">
        <div class="plan-stat-val">${data.carencia_meses || '—'}<span>meses</span></div>
        <div class="plan-stat-label">Carencia (de 180)</div>
      </div>
      <div class="plan-stat">
        <div class="plan-stat-val">R$<span style="font-size:18px">${sal}</span></div>
        <div class="plan-stat-label">Salario projetado</div>
      </div>
      ${melhor ? `<div class="plan-stat">
        <div class="plan-stat-val" style="color:var(--verde)">${melhor.rmi_formatada}</div>
        <div class="plan-stat-label">RMI estimada (melhor regra)</div>
      </div>` : ''}
    </div>
  </div>

  <div class="card" style="margin-bottom:20px;">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
      <span style="font-size:13px;font-weight:600;color:var(--cinza-600)">Progresso do Tempo de Contribuição</span>
      <span style="font-size:13px;font-weight:700;color:var(--azul)">${pct}% de 35 anos</span>
    </div>
    <div class="tc-progress-bar">
      <div class="tc-progress-fill" style="width:${pct}%"></div>
    </div>
    <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--cinza-400);margin-top:4px;">
      <span>${tc.anos}a ${tc.meses}m atuais</span>
      <span>Meta: 35 anos</span>
    </div>
    <details style="margin-top:8px;cursor:pointer;">
      <summary style="font-size:11px;color:#1e40af;font-weight:600;">📜 Fundamentação legal da contagem de TC</summary>
      <div style="margin-top:8px;font-size:11px;color:#374151;background:#eff6ff;padding:10px;border-radius:6px;line-height:1.6;">
        <strong>Metodologia de contagem conforme legislação vigente:</strong><br>
        • <strong>Empregado CLT/Avulso/Doméstico:</strong> TC conta em dias corridos do período (Art. 60, Decreto 3.048/99)<br>
        • <strong>Facultativo/CI/MEI:</strong> TC conta por competências com contribuição efetiva — 30 dias/mês (Art. 19-C, Decreto 10.410/2020)<br>
        • <strong>Contribuição abaixo do SM:</strong> Pós-EC 103/2019, NÃO conta para TC nem carência (Art. 19-E, Decreto 3.048/99)<br>
        • <strong>Auxílio-doença intercalado:</strong> Conta como TC quando entre períodos de contribuição (Art. 60 §3º, Lei 8.213/91)<br>
        • <strong>Períodos concomitantes:</strong> Contados apenas uma vez — sem duplicação<br>
        • <strong>Indicadores CNIS:</strong> PREC-MENOR-MIN, IREC-INDPEND excluem contribuições com pendência
      </div>
    </details>
  </div>`;

  // ── Análise TC vs Carência (compacto, dentro do card de TC) ────────────────
  if (data.analise_tc_carencia) {
    const atc = data.analise_tc_carencia;
    const pctCar = Math.min(100, Math.round((atc.carencia_meses / atc.carencia_exigida) * 100));
    const temB31 = atc.dias_b31_intercalado > 0;
    const corCar = atc.carencia_ok ? '#22c55e' : '#ef4444';

    html += `<div class="card" style="border-left:4px solid ${atc.carencia_ok ? '#10b981' : '#ef4444'};padding:16px 20px;">
      <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-bottom:10px;">
        <h3 class="card-title" style="margin:0;">TC vs Carencia</h3>
        ${!atc.carencia_ok && temB31 ? `<span style="background:#fef2f2;color:#dc2626;font-size:11px;font-weight:700;padding:3px 10px;border-radius:12px;">GARGALO: CARENCIA</span>` : ''}
      </div>

      <div style="display:flex;gap:24px;flex-wrap:wrap;align-items:flex-start;">
        <!-- TC -->
        <div style="flex:1;min-width:180px;">
          <div style="font-size:11px;color:#6b7280;margin-bottom:2px;">Tempo de Contribuicao</div>
          <div style="font-size:22px;font-weight:800;color:#1e3a8a;">${atc.tc_total_texto}</div>
          ${temB31 ? `<div style="font-size:11px;color:#3b82f6;margin-top:2px;">Inclui ${atc.meses_b31_intercalado}m de aux.-doenca (B31)</div>` : ''}
        </div>
        <!-- Carência -->
        <div style="flex:1;min-width:220px;">
          <div style="font-size:11px;color:#6b7280;margin-bottom:2px;">Carencia</div>
          <div style="display:flex;align-items:baseline;gap:6px;">
            <span style="font-size:22px;font-weight:800;color:${corCar};">${atc.carencia_meses}</span>
            <span style="font-size:13px;color:#6b7280;">de ${atc.carencia_exigida} meses</span>
            ${!atc.carencia_ok ? `<span style="font-size:12px;color:#dc2626;font-weight:600;">(faltam ${atc.faltam_carencia})</span>` : `<span style="font-size:12px;color:#16a34a;font-weight:600;">OK</span>`}
          </div>
          <div style="background:${atc.carencia_ok ? '#dcfce7' : '#fecaca'};border-radius:4px;height:6px;overflow:hidden;margin-top:6px;">
            <div style="background:${corCar};height:100%;width:${pctCar}%;border-radius:4px;"></div>
          </div>
        </div>
      </div>`;

    // B31 + explicação em details compacto
    if (temB31) {
      html += `<details style="margin-top:12px;cursor:pointer;border-top:1px solid #e5e7eb;padding-top:10px;">
        <summary style="font-size:12px;color:#1e40af;font-weight:600;">Ver detalhes: por que TC e Carencia sao diferentes?</summary>
        <div style="margin-top:10px;font-size:12px;color:#374151;line-height:1.6;">
          <strong>TC</strong> inclui periodos de auxilio-doenca intercalados (Art. 60 par. 3, Lei 8.213/91).<br>
          <strong>Carencia</strong> conta apenas contribuicoes efetivamente pagas (Art. 29 par. 5, Lei 8.213/91).<br>
          Dos <strong>${atc.tc_total_texto}</strong> de TC, <strong>${atc.meses_b31_intercalado} meses</strong> sao B31 — por isso a carencia (${atc.carencia_meses}) e menor.
        </div>`;

      if (atc.beneficios_b31?.length) {
        html += `<table style="width:100%;font-size:11px;border-collapse:collapse;margin-top:10px;">
          <thead><tr style="background:#f3f4f6;">
            <th style="padding:4px 8px;text-align:left;">DIB</th>
            <th style="padding:4px 8px;text-align:left;">DCB</th>
            <th style="padding:4px 8px;text-align:right;">Dias</th>
            <th style="padding:4px 8px;text-align:left;">Conta como</th>
          </tr></thead><tbody>`;
        atc.beneficios_b31.forEach(b => {
          html += `<tr>
            <td style="padding:3px 8px;">${b.dib}</td>
            <td style="padding:3px 8px;">${b.dcb}</td>
            <td style="padding:3px 8px;text-align:right;font-weight:600;">${b.dias}</td>
            <td style="padding:3px 8px;"><span style="color:#2563eb;">TC: sim</span> | <span style="color:#dc2626;">Carencia: nao</span></td>
          </tr>`;
        });
        html += `</tbody></table>`;
      }
      html += `</details>`;
    }

    html += `</div>`;
  }

  // ── Score de Prontidão Previdenciária (EXCLUSIVO) ──────────────────────────
  if (data.score_prontidao) {
    const sp = data.score_prontidao;
    const angulo = (sp.score / 1000) * 180;
    const comp = sp.componentes || {};
    html += `<div class="card" style="border:2px solid ${sp.cor};position:relative;overflow:hidden;">
      <div style="position:absolute;top:0;right:0;background:${sp.cor};color:#fff;padding:4px 12px;border-radius:0 0 0 8px;font-size:10px;font-weight:700;letter-spacing:1px;">EXCLUSIVO SistPrev</div>
      <h3 class="card-title" style="margin-bottom:16px;">🎯 Score de Prontidão Previdenciária</h3>
      <div style="display:flex;align-items:center;gap:30px;flex-wrap:wrap;">
        <div style="text-align:center;min-width:180px;">
          <div style="position:relative;width:160px;height:90px;margin:0 auto;">
            <svg viewBox="0 0 160 90" style="width:160px;height:90px;">
              <path d="M10,85 A70,70 0 0,1 150,85" fill="none" stroke="#e5e7eb" stroke-width="12" stroke-linecap="round"/>
              <path d="M10,85 A70,70 0 0,1 150,85" fill="none" stroke="${sp.cor}" stroke-width="12" stroke-linecap="round"
                stroke-dasharray="${angulo * 2.18}" stroke-dashoffset="0"
                style="transition:stroke-dasharray 1s ease;"/>
            </svg>
            <div style="position:absolute;bottom:0;left:50%;transform:translateX(-50%);text-align:center;">
              <div style="font-size:36px;font-weight:900;color:${sp.cor};line-height:1;">${sp.score}</div>
              <div style="font-size:10px;color:#9ca3af;">de 1000</div>
            </div>
          </div>
          <div style="margin-top:8px;font-size:13px;font-weight:700;color:${sp.cor};">${sp.classificacao?.replace('_',' ') || ''}</div>
          <div style="font-size:12px;color:#6b7280;margin-top:2px;">${sp.mensagem || ''}</div>
        </div>
        <div style="flex:1;min-width:280px;">
          <div style="font-size:11px;font-weight:600;color:#6b7280;margin-bottom:8px;">COMPONENTES DO SCORE</div>`;
    for (const [key, c] of Object.entries(comp)) {
      const pctBar = Math.round((c.pontos / c.maximo) * 100);
      const labels = {
        tempo_contribuicao: '⏱️ Tempo de Contribuição',
        idade: '🎂 Idade',
        carencia: '📋 Carência',
        qualidade_segurado: '🛡️ Qualidade Segurado',
        proximidade: '📍 Proximidade',
        valor_beneficio: '💰 Valor Benefício',
      };
      html += `<div style="margin-bottom:6px;">
        <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:2px;">
          <span>${labels[key] || key}</span>
          <span style="font-weight:700;">${c.pontos}/${c.maximo}</span>
        </div>
        <div style="background:#e5e7eb;border-radius:4px;height:8px;overflow:hidden;">
          <div style="background:${sp.cor};height:100%;width:${pctBar}%;border-radius:4px;transition:width 0.8s ease;"></div>
        </div>
        <div style="font-size:10px;color:#9ca3af;margin-top:1px;">${c.detalhe || ''}</div>
      </div>`;
    }
    // Disclaimer do score
    const disclaimerScore = sp.disclaimer || '';
    if (disclaimerScore) {
      html += `<div style="font-size:10px;color:#9ca3af;margin-top:8px;padding:6px 8px;background:#f9fafb;border-radius:4px;font-style:italic;">${disclaimerScore}</div>`;
    }
    // Alertas do score
    if (sp.alertas && sp.alertas.length > 0) {
      sp.alertas.forEach(a => {
        html += `<div style="font-size:11px;color:#dc2626;margin-top:4px;padding:4px 8px;background:#fef2f2;border-radius:4px;">⚠️ ${a}</div>`;
      });
    }
    html += `</div></div></div>`;
  }

  // ── Recomendacao ──────────────────────────────────────────────────────────
  if (data.recomendacao) {
    html += `<div class="recomendacao-box ${data.elegiveis_agora?'elegivel-hoje':''}">${data.recomendacao}</div>`;
  }

  // ── Marcos Legais — TC em cada data-chave ────────────────────────────────
  if (data.marcos_legais?.length) {
    html += `<div class="card">
      <h3 class="card-title">📜 Tempo de Contribuição nos Marcos Legais</h3>
      <p class="card-desc">Análise do tempo acumulado em cada data-chave da legislação previdenciária. Fundamental para definir direitos adquiridos e regras aplicáveis.</p>
      <div style="overflow-x:auto;">
      <table class="tabela-planejamento">
        <thead><tr>
          <th>Marco Legal</th><th>Data</th><th>TC Acumulado</th>
          <th>Contribuições</th><th>Idade</th><th>Análise</th>
        </tr></thead>
        <tbody>`;
    data.marcos_legais.forEach(m => {
      const isDer = m.sigla === 'DER';
      const bg = isDer ? 'background:#f0f4ff;' : '';
      html += `<tr style="${bg}">
        <td><strong>${m.sigla}</strong><br><small style="color:#6b7280">${m.nome}</small></td>
        <td style="white-space:nowrap;">${m.data}</td>
        <td style="font-weight:700;white-space:nowrap;">${m.tc_texto || '—'}</td>
        <td style="text-align:center;">${m.contribuicoes ?? '—'}</td>
        <td style="text-align:center;">${m.idade_anos ?? '—'} anos</td>
        <td style="font-size:12px;">${m.observacao || m.relevancia || ''}</td>
      </tr>`;
    });
    html += `</tbody></table></div></div>`;
  }

  // ── Competências sem Salário ──────────────────────────────────────────────
  if (data.competencias_sem_salario) {
    const cs = data.competencias_sem_salario;
    const temProblema = cs.total_problemas > 0;
    const borderCor = temProblema ? '#f59e0b' : '#10b981';
    html += `<div class="card" style="border-left:4px solid ${borderCor};">
      <h3 class="card-title">${temProblema ? '⚠️' : '✅'} Competências sem Salário de Contribuição</h3>
      <div style="font-size:13px;color:#374151;margin-bottom:12px;">${cs.mensagem || ''}</div>`;
    if (temProblema) {
      html += `<div style="font-size:12px;color:#92400e;background:#fef3c7;padding:10px 14px;border-radius:8px;margin-bottom:12px;">
        <strong>💡 Impacto:</strong> ${cs.impacto || ''}</div>`;
    }
    if (cs.sem_salario?.length) {
      html += `<div style="margin-bottom:10px;">
        <div style="font-size:12px;font-weight:600;color:#991b1b;margin-bottom:6px;">Competências SEM salário (${cs.sem_salario.length}):</div>
        <div style="display:flex;flex-wrap:wrap;gap:4px;">`;
      cs.sem_salario.forEach(s => {
        html += `<span style="background:#fef2f2;color:#991b1b;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;">${s.competencia}</span>`;
      });
      html += `</div>
        <div style="font-size:11px;color:#6b7280;margin-top:4px;">Empregador: ${cs.sem_salario[0]?.empregador || '—'}</div>
      </div>`;
    }
    if (cs.abaixo_minimo?.length) {
      html += `<div>
        <div style="font-size:12px;font-weight:600;color:#b45309;margin-bottom:6px;">Valores suspeitos (${cs.abaixo_minimo.length}):</div>
        <div style="display:flex;flex-wrap:wrap;gap:4px;">`;
      cs.abaixo_minimo.forEach(s => {
        html += `<span style="background:#fef3c7;color:#92400e;padding:2px 8px;border-radius:4px;font-size:11px;">${s.competencia} (R$ ${s.valor})</span>`;
      });
      html += `</div></div>`;
    }
    html += `</div>`;
  }

  // ── Linha do tempo ────────────────────────────────────────────────────────
  if (alcancaveis.length) {
    const maxMeses = alcancaveis[alcancaveis.length - 1].meses_faltantes || 1;
    html += `<div class="card"><h3 class="card-title">📅 Linha do Tempo — Datas de Aposentadoria</h3>`;
    html += `<div class="timeline">`;
    alcancaveis.forEach((p, i) => {
      const isMelhor = i === 0;
      const baraPct = Math.round((p.meses_faltantes / maxMeses) * 100);
      const msg = p.mensagem_cliente || '';
      html += `
        <div class="timeline-item ${isMelhor ? 'timeline-melhor' : ''}">
          <div class="timeline-dot ${isMelhor ? 'dot-verde' : 'dot-azul'}"></div>
          <div class="timeline-content">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
              <div>
                <div class="timeline-data">${p.data_elegibilidade}</div>
                <div class="timeline-regra">${p.regra}</div>
              </div>
              <div style="text-align:right;flex-shrink:0;">
                <div class="timeline-rmi">${p.rmi_formatada}</div>
                ${isMelhor ? '<span class="badge badge-ok" style="display:inline-block;margin-top:4px;">⭐ Melhor opção</span>' : ''}
              </div>
            </div>
            <div class="timeline-periodo">Faltam: <strong>${p.texto_faltante || 'menos de 1 mês'}</strong></div>
            <div class="tc-progress-bar" style="margin-top:8px;">
              <div class="tc-progress-fill ${isMelhor?'':'tc-progress-azul'}" style="width:${baraPct}%"></div>
            </div>
            ${msg ? `<div class="timeline-msg">${msg}</div>` : ''}
          </div>
        </div>`;
    });
    html += `</div></div>`;
  }

  // ── Tabela comparativa ────────────────────────────────────────────────────
  html += `<div class="card">
    <h3 class="card-title">📊 Comparativo por Regra</h3>
    <table class="tabela-planejamento">
      <thead><tr><th>Regra</th><th>Data</th><th>Tempo Faltando</th><th>RMI Estimada</th></tr></thead>
      <tbody>`;
  (data.projecoes||[]).sort((a,b) => {
    if (a.meses_faltantes && b.meses_faltantes) return a.meses_faltantes - b.meses_faltantes;
    if (a.meses_faltantes) return -1;
    return 1;
  }).forEach((p, i) => {
    const ok = !!p.data_elegibilidade;
    const isMelhor = ok && i === 0;
    html += `<tr class="${isMelhor?'melhor-linha':''}">
      <td>${isMelhor ? '⭐ ' : ''}${p.regra}</td>
      <td>${p.data_elegibilidade || '—'}</td>
      <td>${p.texto_faltante || '—'}</td>
      <td><strong class="${ok?'text-verde':'text-vermelho'}">${p.rmi_formatada || '—'}</strong></td>
    </tr>`;
  });
  html += `</tbody></table></div>`;

  // ── Argumentos para o cliente ─────────────────────────────────────────────
  if (data.argumentos_cliente?.length) {
    html += `<div class="card">
      <h3 class="card-title">💬 Argumentos para Apresentar ao Cliente</h3>
      <p class="card-desc">Use estes pontos para explicar o planejamento ao seu cliente de forma clara e objetiva.</p>
      <ul class="argumentos-lista">`;
    data.argumentos_cliente.forEach((arg, i) => {
      html += `<li class="argumento-item"><span class="argumento-num">${i+1}</span><span>${arg}</span></li>`;
    });
    html += `</ul></div>`;
  }

  // ── Custo-Benefício ───────────────────────────────────────────────────────
  if (data.custo_beneficio?.length) {
    const ev = data.expectativa_vida || {};
    const evAnos = ev.anos || 76.6;
    const evSexo = ev.sexo === 'FEMININO' ? 'mulheres' : 'homens';
    html += `<div class="card">
      <h3 class="card-title">💰 Custo-Benefício — Vale a Pena Contribuir?</h3>
      <p class="card-desc">Expectativa de vida IBGE 2024: <strong>${evAnos} anos</strong> para ${evSexo}. Mostra quanto você paga até a aposentadoria e quanto recebe até o fim da vida.</p>`;

    data.custo_beneficio.forEach(cb => {
      html += `<div style="margin-bottom:20px;">
        <div style="background:#f0f4ff;border-radius:8px;padding:10px 14px;margin-bottom:8px;display:flex;flex-wrap:wrap;gap:16px;font-size:13px;">
          <span>📅 Aposentadoria: <strong>${cb.data_elegibilidade || '—'}</strong></span>
          <span>🎂 Idade: <strong>${cb.idade_aposentadoria ? cb.idade_aposentadoria.toFixed(1) : '—'} anos</strong></span>
          <span>📆 Meses recebendo: <strong>${cb.meses_recebendo ? Math.round(cb.meses_recebendo) : '—'}</strong></span>
          <span>💵 Total recebido: <strong>R$ ${fmtDecimal(cb.total_recebido || '0')}</strong></span>
        </div>
        <div style="font-size:13px;font-weight:700;color:#1a3c6e;margin-bottom:6px;">${cb.regra || ''}</div>
        <div style="overflow-x:auto;">
        <table class="tabela-planejamento">
          <thead><tr>
            <th>Modalidade</th><th>Alíquota</th><th>Contrib/mês</th>
            <th>Total Pago</th><th>Total Recebido</th>
            <th>Lucro</th><th>ROI</th><th>Recupera em</th><th>Vale?</th>
          </tr></thead>
          <tbody>`;
      (cb.modalidades || []).forEach(m => {
        const ok = m.vale_a_pena;
        const bg = ok ? 'background:#f0fdf4' : 'background:#fef2f2';
        const cor = ok ? 'color:#065f46' : 'color:#991b1b';
        html += `<tr style="${bg}">
          <td><strong>${m.modalidade || ''}</strong></td>
          <td>${m.aliquota_pct || 0}%</td>
          <td>R$ ${fmtDecimal(m.contribuicao_mensal || '0')}</td>
          <td>R$ ${fmtDecimal(m.total_pago_ate_apos || '0')}</td>
          <td>R$ ${fmtDecimal(m.total_recebido_ate_obito || '0')}</td>
          <td style="${cor};font-weight:700">R$ ${fmtDecimal(m.lucro_liquido || '0')}</td>
          <td style="${cor};font-weight:700">${m.roi_percentual || 0}%</td>
          <td>${m.anos_para_recuperar || 0} anos</td>
          <td style="${cor};font-weight:700">${ok ? '✅ Sim' : '❌ Não'}</td>
        </tr>`;
      });
      html += `</tbody></table></div>`;
      // Disclaimer do custo-beneficio
      if (cb.disclaimer) {
        html += `<div style="font-size:10px;color:#9ca3af;margin-top:6px;padding:6px 8px;background:#f9fafb;border-radius:4px;font-style:italic;">⚠️ ${cb.disclaimer}</div>`;
      }
      html += `</div>`;
    });
    html += `</div>`;
  }

  // ── Resumo Executivo ─────────────────────────────────────────────────────
  if (data.resumo_executivo) {
    const re = data.resumo_executivo;
    html += `<div class="card" style="border-left:4px solid #1d4ed8;">
      <h3 class="card-title">📋 Resumo Executivo</h3>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
        <div style="background:#f0f4ff;padding:14px;border-radius:8px;">
          <div style="font-size:11px;color:#6b7280;margin-bottom:4px;font-weight:600;">SITUAÇÃO ATUAL</div>
          <div style="font-size:13px;">${re.situacao_atual || '—'}</div>
        </div>
        <div style="background:#f0fdf4;padding:14px;border-radius:8px;">
          <div style="font-size:11px;color:#6b7280;margin-bottom:4px;font-weight:600;">MELHOR CAMINHO</div>
          <div style="font-size:13px;">${re.melhor_caminho || '—'}</div>
        </div>
        <div style="background:#fef3c7;padding:14px;border-radius:8px;">
          <div style="font-size:11px;color:#6b7280;margin-bottom:4px;font-weight:600;">AÇÃO IMEDIATA</div>
          <div style="font-size:13px;">${re.acao_imediata || '—'}</div>
        </div>
        <div style="background:#ede9fe;padding:14px;border-radius:8px;">
          <div style="font-size:11px;color:#6b7280;margin-bottom:4px;font-weight:600;">PRÓXIMO PASSO</div>
          <div style="font-size:13px;">${re.proximo_passo || '—'}</div>
        </div>
      </div>
    </div>`;
  }

  // ── Qualidade de Segurado ─────────────────────────────────────────────────
  if (data.qualidade_segurado) {
    const qs = data.qualidade_segurado;
    const statusCor = qs.status === 'ATIVA' ? '#065f46' : qs.status === 'EM_RISCO' ? '#b45309' : '#991b1b';
    const statusBg = qs.status === 'ATIVA' ? '#f0fdf4' : qs.status === 'EM_RISCO' ? '#fef3c7' : '#fef2f2';
    const statusIcon = qs.status === 'ATIVA' ? '✅' : qs.status === 'EM_RISCO' ? '⚠️' : '❌';
    html += `<div class="card">
      <h3 class="card-title">🛡️ Qualidade de Segurado</h3>
      <div style="background:${statusBg};padding:14px 18px;border-radius:8px;border-left:4px solid ${statusCor};margin-bottom:12px;">
        <div style="font-size:15px;font-weight:700;color:${statusCor};margin-bottom:4px;">${statusIcon} ${qs.status || '—'}</div>
        <div style="font-size:13px;color:#374151;">${qs.mensagem || ''}</div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;font-size:13px;">
        <div><strong>Última contribuição:</strong><br>${qs.ultima_contribuicao || '—'}</div>
        <div><strong>Período de graça:</strong><br>${qs.periodo_graca_meses || 0} meses</div>
        <div><strong>Perda da qualidade em:</strong><br>${qs.data_perda_qualidade || '—'}</div>
      </div>
    </div>`;
  }

  // ── Cenários de Vida Quantificados ────────────────────────────────────────
  if (data.cenarios_vida?.length) {
    html += `<div class="card">
      <h3 class="card-title">📊 Cenários de Contribuição — Comparativo com Valores</h3>
      <p class="card-desc">Quanto custa cada forma de contribuição e como impacta na sua aposentadoria.</p>
      <div style="overflow-x:auto;">
      <table class="tabela-planejamento">
        <thead><tr>
          <th>Cenário</th><th>Custo/mês</th><th>Custo/ano</th><th>Total até aposentar</th>
          <th>Impacto na Data</th><th>Impacto na RMI</th>
        </tr></thead>
        <tbody>`;
    data.cenarios_vida.forEach(cv => {
      html += `<tr>
        <td><strong>${cv.cenario || cv.nome || ''}</strong><br><small style="color:#6b7280">${cv.descricao || ''}</small></td>
        <td>R$ ${fmtDecimal(cv.custo_mensal || cv.monthly_cost || '0')}</td>
        <td>R$ ${fmtDecimal(cv.custo_anual || cv.annual_cost || '0')}</td>
        <td>R$ ${fmtDecimal(cv.custo_total || cv.total_cost_until_retirement || '0')}</td>
        <td>${cv.impacto_data || cv.impact_on_date || '—'}</td>
        <td>${cv.impacto_rmi || cv.impact_on_rmi || '—'}</td>
      </tr>`;
    });
    html += `</tbody></table></div></div>`;
  }

  // ── Pensão por Morte Projetada ────────────────────────────────────────────
  if (data.pensao_projetada) {
    const pp = data.pensao_projetada;
    html += `<div class="card">
      <h3 class="card-title">👨‍👩‍👧‍👦 Pensão por Morte — Projeção</h3>
      <p class="card-desc">${pp.mensagem || 'Quanto seus dependentes receberiam se algo acontecesse.'}</p>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px;">`;
    (pp.cenarios || []).forEach(c => {
      html += `<div style="background:#f0f4ff;padding:14px;border-radius:8px;text-align:center;">
        <div style="font-size:24px;font-weight:800;color:#1a3c6e;">${c.valor_formatado || 'R$ ' + fmtDecimal(c.valor || '0')}</div>
        <div style="font-size:12px;color:#6b7280;margin-top:4px;">${c.dependentes} dependente${c.dependentes > 1 ? 's' : ''} (${c.cota_pct}%)</div>
      </div>`;
    });
    html += `</div></div>`;
  }

  // ── Plano de Ação ─────────────────────────────────────────────────────────
  if (data.plano_acao?.length) {
    html += `<div class="card">
      <h3 class="card-title">✅ Plano de Ação — Próximos Passos</h3>
      <p class="card-desc">Siga estes passos para garantir a melhor aposentadoria possível.</p>`;
    data.plano_acao.forEach(p => {
      const urgCor = p.urgencia === 'ALTA' ? '#991b1b' : p.urgencia === 'MEDIA' ? '#b45309' : '#065f46';
      const urgBg = p.urgencia === 'ALTA' ? '#fef2f2' : p.urgencia === 'MEDIA' ? '#fef3c7' : '#f0fdf4';
      html += `<div style="display:flex;gap:14px;padding:14px;border-bottom:1px solid #f3f4f6;align-items:flex-start;">
        <div style="background:#1a3c6e;color:#fff;width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;flex-shrink:0;">${p.numero}</div>
        <div style="flex:1;">
          <div style="font-weight:700;font-size:14px;margin-bottom:4px;">${p.titulo || ''}</div>
          <div style="font-size:13px;color:#374151;line-height:1.6;">${p.descricao || ''}</div>
          <div style="display:flex;gap:12px;margin-top:6px;font-size:11px;">
            ${p.prazo ? `<span style="color:#6b7280;">⏰ ${p.prazo}</span>` : ''}
            <span style="background:${urgBg};color:${urgCor};padding:2px 8px;border-radius:4px;font-weight:600;">Urgência: ${p.urgencia}</span>
          </div>
        </div>
      </div>`;
    });
    html += `</div>`;
  }

  // ── Análise de Atividade Especial por Vínculo ─────────────────────────────
  if (data.analise_especial?.length) {
    html += `<div class="card" style="border:2px solid #b45309;position:relative;overflow:hidden;">
      <div style="position:absolute;top:0;right:0;background:#b45309;color:#fff;padding:4px 12px;border-radius:0 0 0 8px;font-size:10px;font-weight:700;letter-spacing:1px;">EXCLUSIVO SistPrev</div>
      <h3 class="card-title">🏭 Análise de Atividade Especial por Empregador</h3>
      <p class="card-desc">O sistema analisou cada empregador do CNIS e identificou possíveis atividades especiais. <strong>Clique em "Aplicar" para marcar o vínculo como especial e recalcular automaticamente.</strong></p>
      <div style="overflow-x:auto;">
      <table class="tabela-planejamento">
        <thead><tr><th>Empregador</th><th>Período</th><th>Probabilidade</th><th>Agentes Prováveis</th><th>Atividade Atual</th><th>Aplicar Fator</th></tr></thead>
        <tbody>`;
    // Ordenar: ALTA primeiro, depois MEDIA, BAIXA, NENHUMA
    const probOrdem = {'ALTA':0,'MEDIA':1,'BAIXA':2,'NENHUMA':3};
    const especOrdenada = [...data.analise_especial].sort((a,b) => (probOrdem[a.probabilidade]||3) - (probOrdem[b.probabilidade]||3));
    const comEspecial = especOrdenada.filter(ae => ae.probabilidade !== 'NENHUMA');
    const semEspecial = especOrdenada.filter(ae => ae.probabilidade === 'NENHUMA');

    especOrdenada.forEach((ae, aeIdx) => {
      const isNone = ae.probabilidade === 'NENHUMA';
      const probCor = ae.probabilidade === 'ALTA' ? '#991b1b' : ae.probabilidade === 'MEDIA' ? '#b45309' : isNone ? '#6b7280' : '#065f46';
      const probBg = ae.probabilidade === 'ALTA' ? '#fef2f2' : ae.probabilidade === 'MEDIA' ? '#fef3c7' : isNone ? '#f3f4f6' : '#f0fdf4';
      const rowBg = isNone ? 'opacity:0.7;' : '';
      const fatorInfo = ae.fator_conversao && !isNone ? `<br><small style="color:#7c3aed;">Fator: ${ae.fator_conversao.masculino || '1.4'}(H) / ${ae.fator_conversao.feminino || '1.2'}(M)</small>` : '';
      // Encontrar o vínculo correspondente no state para mostrar atividade atual
      const vIdx = state.vinculos.findIndex(v => v.empregador_cnpj === ae.cnpj || (v.empregador_nome && ae.empregador && v.empregador_nome.toUpperCase().includes(ae.empregador.toUpperCase().substring(0,15))));
      const vAtual = vIdx >= 0 ? state.vinculos[vIdx] : null;
      const atividadeAtual = vAtual?.tipo_atividade || 'NORMAL';
      const isEspecial = atividadeAtual !== 'NORMAL';
      const labelAtual = isEspecial ? `<span style="color:#7c3aed;font-weight:700;">${atividadeAtual.replace('ESPECIAL_','Esp ')}</span>` : '<span style="color:#6b7280;">Normal</span>';
      html += `<tr style="${rowBg}">
        <td><strong>${ae.empregador || '—'}</strong><br><small style="color:#6b7280">${ae.cnpj || ''}</small>
          ${ae.cargo_ctps ? `<br><small style="color:#1e40af;font-weight:600;">Cargo: ${ae.cargo_ctps}</small>` : ''}
          ${ae.via_cargo ? `<br><small style="color:#dc2626;font-weight:700;">Detectado pelo CARGO</small>` : ''}
          ${ae.padroes_encontrados?.length ? `<br><small style="color:#7c3aed;font-weight:600;">${ae.padroes_encontrados.join(', ')}</small>` : ''}</td>
        <td style="white-space:nowrap;">${ae.data_inicio || '—'} a ${ae.data_fim || 'atual'}</td>
        <td><span style="background:${probBg};color:${probCor};padding:2px 10px;border-radius:4px;font-weight:700;font-size:12px;">${ae.probabilidade}</span>${fatorInfo}</td>
        <td style="font-size:12px;">${(ae.agentes_provaveis||[]).join(', ') || '—'}</td>
        <td style="text-align:center;">${labelAtual}</td>
        <td style="white-space:nowrap;text-align:center;">${vIdx >= 0 ? `
          <select onchange="aplicarFatorEspecial(${vIdx}, this.value)" style="font-size:11px;padding:4px 6px;border-radius:4px;border:1px solid #d1d5db;font-weight:600;${isEspecial ? 'background:#ede9fe;color:#7c3aed;' : ''}">
            <option value="NORMAL" ${atividadeAtual==='NORMAL'?'selected':''}>Normal</option>
            <option value="ESPECIAL_25" ${atividadeAtual==='ESPECIAL_25'?'selected':''}>Esp 25a (1.4H/1.2M)</option>
            <option value="ESPECIAL_20" ${atividadeAtual==='ESPECIAL_20'?'selected':''}>Esp 20a (1.75H/1.5M)</option>
            <option value="ESPECIAL_15" ${atividadeAtual==='ESPECIAL_15'?'selected':''}>Esp 15a (2.33H/2.0M)</option>
          </select>` : '—'}</td>
      </tr>`;
      // Jurisprudências expandíveis para cada vínculo com match
      if (ae.jurisprudencias?.length) {
        html += `<tr style="${rowBg}"><td colspan="5" style="padding:0 12px 12px 12px;">
          <div style="background:#eff6ff;border-radius:8px;padding:10px 14px;border-left:4px solid #1e40af;">
            <div style="font-size:12px;font-weight:700;color:#1e40af;margin-bottom:8px;">📚 JURISPRUDÊNCIA CONSOLIDADA (${ae.jurisprudencias.length} referência${ae.jurisprudencias.length>1?'s':''})</div>`;
        ae.jurisprudencias.forEach(j => {
          html += `<div style="background:#fff;padding:8px 12px;border-radius:6px;margin-bottom:6px;border:1px solid #dbeafe;">
            <div style="font-size:11px;font-weight:700;color:#1e40af;">${j.tipo?.replace(/_/g,' ')} ${j.numero} (${j.tribunal})</div>
            ${j.data_julgamento ? `<div style="font-size:10px;color:#6b7280;">Julgado em ${j.data_julgamento}</div>` : ''}
            <div style="font-size:11px;color:#374151;margin-top:4px;">${j.ementa?.substring(0,250)}${j.ementa?.length>250?'...':''}</div>
            ${j.aplicabilidade ? `<div style="font-size:11px;color:#065f46;margin-top:4px;font-style:italic;">➜ ${j.aplicabilidade}</div>` : ''}
            ${j.url ? `<a href="${j.url}" target="_blank" style="font-size:10px;color:#2563eb;text-decoration:underline;">🔗 Ver fonte</a>` : ''}
          </div>`;
        });
        html += `</div></td></tr>`;
      }
    });
    // Resumo
    if (comEspecial.length) {
      html += `</tbody></table></div>
        <div style="margin-top:12px;display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;">
          <div style="background:#fef2f2;padding:10px;border-radius:8px;text-align:center;">
            <div style="font-size:24px;font-weight:800;color:#991b1b;">${comEspecial.length}</div>
            <div style="font-size:11px;color:#991b1b;">Vínculos com indícios de especialidade</div>
          </div>
          <div style="background:#f3f4f6;padding:10px;border-radius:8px;text-align:center;">
            <div style="font-size:24px;font-weight:800;color:#6b7280;">${semEspecial.length}</div>
            <div style="font-size:11px;color:#6b7280;">Sem indícios pelo nome</div>
          </div>
          <div style="background:#ede9fe;padding:10px;border-radius:8px;text-align:center;">
            <div style="font-size:24px;font-weight:800;color:#7c3aed;">${data.analise_especial.length}</div>
            <div style="font-size:11px;color:#7c3aed;">Total de vínculos analisados</div>
          </div>
        </div>`;
    } else {
      html += `</tbody></table></div>`;
    }
    html += `
      <div style="margin-top:12px;padding:10px 14px;background:#fef3c7;border-radius:8px;font-size:12px;color:#92400e;">
        <strong>💡 Importante:</strong> A comprovação de atividade especial requer PPP (Perfil Profissiográfico Previdenciário) e/ou LTCAT. Solicite ao cliente que busque esses documentos junto aos empregadores indicados. Fundamentação: Art. 57 e 58 da Lei 8.213/91.
      </div>
    </div>`;
  }

  // ── Análise Automática de Revisão (quando aposentado) ────────────────────
  if (data.analise_revisao?.beneficio_ativo) {
    const ar = data.analise_revisao;
    html += `<div class="card" style="border:2px solid #7c3aed;position:relative;overflow:hidden;">
      <div style="position:absolute;top:0;right:0;background:#7c3aed;color:#fff;padding:4px 12px;border-radius:0 0 0 8px;font-size:10px;font-weight:700;letter-spacing:1px;">EXCLUSIVO SistPrev</div>
      <h3 class="card-title">🔍 Análise Automática de Revisão do Benefício</h3>
      <p class="card-desc">O segurado já está aposentado (${ar.especie || 'benefício ativo'}). O sistema analisou automaticamente ${ar.revisoes_possiveis?.length || 0} tipos de revisão.</p>`;

    // Decadência
    if (ar.decadencia) {
      const dec = ar.decadencia;
      const decCor = dec.dentro_prazo ? '#065f46' : '#991b1b';
      const decBg = dec.dentro_prazo ? '#f0fdf4' : '#fef2f2';
      html += `<div style="background:${decBg};padding:10px 14px;border-radius:8px;border-left:4px solid ${decCor};margin-bottom:16px;">
        <div style="font-size:13px;font-weight:700;color:${decCor};">${dec.dentro_prazo ? '✅ DENTRO DO PRAZO DECENAL' : '⚠️ FORA DO PRAZO DECENAL'}</div>
        <div style="font-size:12px;color:#374151;margin-top:4px;">${dec.mensagem}</div>
        <div style="font-size:11px;color:#6b7280;margin-top:2px;">${dec.fundamentacao}</div>
      </div>`;
    }

    // Tabela de revisões
    if (ar.revisoes_possiveis?.length) {
      html += `<div style="overflow-x:auto;">
      <table class="tabela-planejamento">
        <thead><tr><th>Tipo de Revisão</th><th>Aplicável?</th><th>Viável?</th><th>Impacto</th><th>Análise</th></tr></thead>
        <tbody>`;
      ar.revisoes_possiveis.forEach(r => {
        const isEncerrada = r.tipo?.includes('ENCERRADA');
        const bg = isEncerrada ? 'background:#f3f4f6;opacity:0.7;' : r.viavel ? 'background:#f0fdf4' : r.aplicavel ? 'background:#fef3c7' : '';
        html += `<tr style="${bg}">
          <td><strong>${r.tipo}</strong><br><small style="color:#6b7280">${r.fundamentacao || ''}</small></td>
          <td style="text-align:center;font-size:18px;">${r.aplicavel ? '✅' : '❌'}</td>
          <td style="text-align:center;font-size:18px;">${r.viavel ? '✅' : '❌'}</td>
          <td style="font-size:12px;font-weight:600;">${r.impacto_estimado || '—'}</td>
          <td style="font-size:12px;">${r.analise || '—'}<br><small style="color:#6b7280">📄 ${r.documentos_necessarios || ''}</small>
            ${r.como_calcular_diferenca ? `<br><details style="margin-top:6px;cursor:pointer;"><summary style="font-size:11px;color:#1e40af;font-weight:600;">Como calcular a diferenca na RMI?</summary><div style="font-size:11px;color:#374151;background:#eff6ff;padding:8px;border-radius:6px;margin-top:4px;line-height:1.6;">${r.como_calcular_diferenca}</div></details>` : ''}</td>
        </tr>`;
      });
      html += `</tbody></table></div>`;
    }

    // Recomendação geral
    if (ar.recomendacao_geral) {
      html += `<div style="margin-top:12px;padding:12px 16px;background:#ede9fe;border-radius:8px;font-size:13px;color:#5b21b6;">
        <strong>📋 Recomendação:</strong> ${ar.recomendacao_geral}
      </div>`;
    }
    html += `</div>`;
  }

  // ── CENÁRIOS DE REVISÃO (quando aposentado) ──────────────────────────────
  if (data.cenarios_revisao?.modo === 'revisao') {
    const cr = data.cenarios_revisao;
    const temRmiInss = cr.rmi_inss && parseFloat(cr.rmi_inss) > 0;
    const mb = cr.melhor_beneficio;
    const difFav = mb?.diferenca_favoravel;

    html += `<div class="card" style="border:3px solid ${difFav ? '#dc2626' : '#2563eb'};position:relative;overflow:hidden;">
      <div style="position:absolute;top:0;right:0;background:${difFav ? '#dc2626' : '#2563eb'};color:#fff;padding:4px 14px;border-radius:0 0 0 8px;font-size:10px;font-weight:700;letter-spacing:1px;">MODO REVISAO</div>
      <h3 class="card-title">Recalculo na DER — Cenarios de Revisao</h3>
      <p class="card-desc">O segurado ja esta aposentado. O sistema recalculou a RMI na DER (${cr.der_revisao}) por TODAS as regras para verificar se o INSS concedeu o melhor beneficio.</p>`;

    // TC na DER
    const tcd = cr.tc_na_der;
    if (tcd) {
      html += `<div style="display:flex;gap:20px;flex-wrap:wrap;margin:12px 0;padding:12px;background:#f0f4ff;border-radius:8px;">
        <div><div style="font-size:11px;color:#6b7280;">TC na DER</div><div style="font-size:20px;font-weight:800;color:#1e3a8a;">${tcd.anos}a ${tcd.meses}m ${tcd.dias}d</div></div>
        ${tcd.dias_especial > 0 ? `<div><div style="font-size:11px;color:#6b7280;">Tempo Especial (convertido)</div><div style="font-size:20px;font-weight:800;color:#7c3aed;">${Math.floor(tcd.dias_especial/365)}a ${Math.floor((tcd.dias_especial%365)/30)}m</div></div>` : ''}
        <div><div style="font-size:11px;color:#6b7280;">Carencia na DER</div><div style="font-size:20px;font-weight:800;color:#065f46;">${cr.carencia_na_der} meses</div></div>
        ${temRmiInss ? `<div><div style="font-size:11px;color:#6b7280;">RMI concedida pelo INSS</div><div style="font-size:20px;font-weight:800;color:#dc2626;">R$ ${fmtDecimal(cr.rmi_inss)}</div></div>` : ''}
      </div>`;
    }

    // Melhor benefício vs INSS
    if (mb && temRmiInss && difFav) {
      html += `<div style="background:#fef2f2;border:2px solid #dc2626;border-radius:10px;padding:16px;margin:12px 0;">
        <div style="font-size:14px;font-weight:800;color:#991b1b;">REVISAO FAVORAVEL — INSS NAO CONCEDEU O MELHOR BENEFICIO</div>
        <div style="display:flex;gap:24px;flex-wrap:wrap;margin-top:10px;">
          <div>
            <div style="font-size:11px;color:#6b7280;">RMI que o INSS deu</div>
            <div style="font-size:22px;font-weight:800;color:#dc2626;">R$ ${fmtDecimal(cr.rmi_inss)}</div>
          </div>
          <div style="display:flex;align-items:center;font-size:24px;color:#6b7280;">→</div>
          <div>
            <div style="font-size:11px;color:#6b7280;">RMI correta (melhor regra)</div>
            <div style="font-size:22px;font-weight:800;color:#16a34a;">R$ ${mb.rmi_formatada}</div>
            <div style="font-size:11px;color:#6b7280;">${mb.regra}</div>
          </div>
          <div>
            <div style="font-size:11px;color:#6b7280;">Diferenca MENSAL</div>
            <div style="font-size:22px;font-weight:800;color:#dc2626;">+ R$ ${fmtDecimal(mb.diferenca_mensal)}</div>
          </div>
        </div>
        ${mb.explicacao ? `<div style="margin-top:10px;font-size:12px;color:#7f1d1d;line-height:1.5;">${mb.explicacao}</div>` : ''}
      </div>`;
      // ── PLANILHA DE DIFERENÇAS MENSAIS ──────────────────────────────
      const difMensal = parseFloat(mb.diferenca_mensal) || 0;
      if (difMensal > 0 && cr.der_revisao) {
        const partsDer = cr.der_revisao.split('/');
        const dibDate = new Date(parseInt(partsDer[2]), parseInt(partsDer[1])-1, parseInt(partsDer[0]));
        const hoje = new Date();
        const meses = [];
        let dt = new Date(dibDate.getFullYear(), dibDate.getMonth(), 1);
        while (dt <= hoje && meses.length < 240) {
          meses.push(new Date(dt));
          dt.setMonth(dt.getMonth() + 1);
        }
        const totalAtrasados = difMensal * meses.length;
        html += `<div style="margin-top:16px;background:#fff7ed;border:2px solid #ea580c;border-radius:10px;padding:16px;">
          <div style="font-size:14px;font-weight:800;color:#9a3412;">PLANILHA DE DIFERENÇAS — Atrasados Estimados</div>
          <div style="display:flex;gap:20px;flex-wrap:wrap;margin:12px 0;">
            <div style="background:#fff;padding:10px 16px;border-radius:8px;border:1px solid #fed7aa;">
              <div style="font-size:11px;color:#9a3412;">Total de meses</div>
              <div style="font-size:22px;font-weight:800;color:#ea580c;">${meses.length}</div>
            </div>
            <div style="background:#fff;padding:10px 16px;border-radius:8px;border:1px solid #fed7aa;">
              <div style="font-size:11px;color:#9a3412;">Diferença mensal</div>
              <div style="font-size:22px;font-weight:800;color:#ea580c;">R$ ${fmtDecimal(mb.diferenca_mensal)}</div>
            </div>
            <div style="background:#fff;padding:10px 16px;border-radius:8px;border:1px solid #fed7aa;">
              <div style="font-size:11px;color:#9a3412;">TOTAL ESTIMADO (sem correção)</div>
              <div style="font-size:22px;font-weight:800;color:#dc2626;">R$ ${fmtDecimal(totalAtrasados.toFixed(2))}</div>
            </div>
          </div>
          <details style="cursor:pointer;">
            <summary style="font-size:12px;font-weight:700;color:#9a3412;">Ver planilha mês a mês (${meses.length} parcelas) ▾</summary>
            <div style="max-height:400px;overflow-y:auto;margin-top:8px;">
            <table style="width:100%;font-size:11px;border-collapse:collapse;">
              <thead><tr style="background:#fed7aa;">
                <th style="padding:4px 8px;text-align:left;">Competência</th>
                <th style="padding:4px 8px;text-align:right;">RMI INSS</th>
                <th style="padding:4px 8px;text-align:right;">RMI Correta</th>
                <th style="padding:4px 8px;text-align:right;">Diferença</th>
                <th style="padding:4px 8px;text-align:right;">Acumulado</th>
              </tr></thead><tbody>`;
        let acumulado = 0;
        const rmiInss = parseFloat(cr.rmi_inss);
        const rmiCorreta = rmiInss + difMensal;
        meses.forEach((m, i) => {
          acumulado += difMensal;
          const comp = String(m.getMonth()+1).padStart(2,'0') + '/' + m.getFullYear();
          html += `<tr style="background:${i%2===0?'#fff':'#fff7ed'};">
            <td style="padding:3px 8px;">${comp}</td>
            <td style="padding:3px 8px;text-align:right;">R$ ${fmtDecimal(rmiInss.toFixed(2))}</td>
            <td style="padding:3px 8px;text-align:right;color:#16a34a;font-weight:600;">R$ ${fmtDecimal(rmiCorreta.toFixed(2))}</td>
            <td style="padding:3px 8px;text-align:right;color:#dc2626;font-weight:600;">R$ ${fmtDecimal(difMensal.toFixed(2))}</td>
            <td style="padding:3px 8px;text-align:right;font-weight:700;">R$ ${fmtDecimal(acumulado.toFixed(2))}</td>
          </tr>`;
        });
        html += `</tbody></table></div></details>
          <div style="margin-top:8px;font-size:11px;color:#78350f;">
            * Valores nominais sem correção monetária (INPC) e juros de mora (Selic). Para cálculo exato dos atrasados com correção, use a aba "Atrasados".
          </div>
        </div>`;
      }
    } else if (mb && temRmiInss && !difFav) {
      html += `<div style="background:#f0fdf4;border:2px solid #22c55e;border-radius:10px;padding:14px;margin:12px 0;">
        <div style="font-size:13px;font-weight:700;color:#166534;">INSS concedeu corretamente o melhor beneficio.</div>
        <div style="font-size:12px;color:#374151;margin-top:4px;">Melhor RMI calculada: R$ ${mb.rmi_formatada} (${mb.regra}). RMI do INSS: R$ ${fmtDecimal(cr.rmi_inss)}.</div>
      </div>`;
    }

    // Tabela de cenários por regra
    const cenElegiveis = (cr.cenarios || []).filter(c => c.elegivel);
    if (cenElegiveis.length) {
      html += `<div style="margin-top:12px;"><div style="font-size:12px;font-weight:700;color:#374151;margin-bottom:8px;">Todas as regras elegiveis na DER:</div>
      <table class="tabela-planejamento"><thead><tr>
        <th>Regra</th><th>RMI Calculada</th>${temRmiInss ? '<th>Diferenca vs INSS</th>' : ''}<th>Coeficiente</th>
      </tr></thead><tbody>`;
      cenElegiveis.sort((a,b) => parseFloat(b.rmi) - parseFloat(a.rmi));
      cenElegiveis.forEach((c, i) => {
        const isMelhor = i === 0;
        const bg = isMelhor ? 'background:#f0fdf4;' : '';
        const dif = c.diferenca_mensal ? parseFloat(c.diferenca_mensal) : 0;
        html += `<tr style="${bg}">
          <td><strong>${c.regra}</strong>${isMelhor ? '<br><small style="color:#16a34a;font-weight:700;">MELHOR BENEFICIO</small>' : ''}<br><small style="color:#6b7280;">${c.base_legal || ''}</small></td>
          <td style="font-size:16px;font-weight:700;color:${isMelhor ? '#16a34a' : '#1e3a8a'};">R$ ${c.rmi_formatada}</td>
          ${temRmiInss ? `<td style="font-weight:700;color:${dif > 0 ? '#dc2626' : dif < 0 ? '#6b7280' : '#16a34a'};">${dif > 0 ? '+' : ''}R$ ${fmtDecimal(c.diferenca_mensal || '0')}</td>` : ''}
          <td>${c.coeficiente ? (parseFloat(c.coeficiente)*100).toFixed(1)+'%' : '—'}</td>
        </tr>`;
      });
      html += `</tbody></table></div>`;
    }

    // Info de conversão especial
    if (cr.especial_info?.vinculos?.length) {
      const ei = cr.especial_info;
      const ganhoDias = ei.total_ganho_dias || 0;
      html += `<div style="margin-top:14px;background:#ede9fe;border-radius:8px;padding:14px;border-left:4px solid #7c3aed;">
        <div style="font-size:13px;font-weight:700;color:#5b21b6;">Conversao de Tempo Especial aplicada</div>
        <div style="font-size:12px;color:#374151;margin-top:6px;">
          ${ei.vinculos.length} vinculo(s) especial(is) convertidos. Ganho total: <strong>${Math.floor(ganhoDias/365)}a ${Math.floor((ganhoDias%365)/30)}m ${ganhoDias%30}d</strong> de TC adicional.
        </div>
        <table style="width:100%;font-size:11px;border-collapse:collapse;margin-top:8px;">
        <thead><tr style="background:rgba(124,58,237,0.1);">
          <th style="padding:4px 8px;text-align:left;">Empregador</th>
          <th style="padding:4px 8px;">Periodo</th>
          <th style="padding:4px 8px;">Tipo</th>
          <th style="padding:4px 8px;">Fator</th>
          <th style="padding:4px 8px;">Dias Reais</th>
          <th style="padding:4px 8px;">Convertidos</th>
          <th style="padding:4px 8px;">Ganho</th>
        </tr></thead><tbody>`;
      ei.vinculos.forEach(v => {
        html += `<tr>
          <td style="padding:3px 8px;">${v.empregador}</td>
          <td style="padding:3px 8px;font-size:10px;">${v.periodo}</td>
          <td style="padding:3px 8px;">${v.tipo}</td>
          <td style="padding:3px 8px;font-weight:700;color:#7c3aed;">${parseFloat(v.fator).toFixed(2)}</td>
          <td style="padding:3px 8px;text-align:center;">${v.dias_reais}</td>
          <td style="padding:3px 8px;text-align:center;font-weight:700;">${v.dias_convertidos}</td>
          <td style="padding:3px 8px;color:#16a34a;font-weight:700;">${v.ganho_texto}</td>
        </tr>`;
      });
      html += `</tbody></table>
        <div style="font-size:11px;color:#6b7280;margin-top:6px;">Fundamentacao: Art. 57 Lei 8.213/91; Art. 70 Decreto 3.048/99; STJ Tema 422. Conversao valida para periodos ate 13/11/2019 (EC 103/2019, Art. 25, par. 2).</div>
      </div>`;
    }

    html += `</div>`;
  }

  // ── Memória de Cálculo Detalhada ─────────────────────────────────────────
  if (data.memoria_calculo?.linhas?.length) {
    const mc = data.memoria_calculo;
    const descarte = mc.descarte || {};
    html += `<div class="card" style="border:2px solid #1a3c6e;position:relative;overflow:hidden;">
      <div style="position:absolute;top:0;right:0;background:#1a3c6e;color:#fff;padding:4px 12px;border-radius:0 0 0 8px;font-size:10px;font-weight:700;letter-spacing:1px;">EXCLUSIVO SistPrev</div>
      <h3 class="card-title">📊 Memória de Cálculo — Correção Monetária</h3>
      <p class="card-desc">Tabela completa com ${mc.total_contribuicoes} contribuições corrigidas pelo INPC até a DER. ${mc.fundamentacao || ''}</p>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px;margin-bottom:16px;">
        <div style="background:#f0f4ff;padding:12px;border-radius:8px;text-align:center;">
          <div style="font-size:11px;color:#6b7280;font-weight:600;">MÉDIA 80% MAIORES</div>
          <div style="font-size:20px;font-weight:800;color:#1a3c6e;">R$ ${fmtDecimal(mc.media_80_maiores)}</div>
          <div style="font-size:10px;color:#9ca3af;">Regra pré-reforma</div>
        </div>
        <div style="background:#f0f4ff;padding:12px;border-radius:8px;text-align:center;">
          <div style="font-size:11px;color:#6b7280;font-weight:600;">MÉDIA 100%</div>
          <div style="font-size:20px;font-weight:800;color:#4F81BD;">R$ ${fmtDecimal(mc.media_100)}</div>
          <div style="font-size:10px;color:#9ca3af;">Regra EC 103/2019</div>
        </div>`;
    if (descarte.aplicado) {
      html += `
        <div style="background:#f0fdf4;padding:12px;border-radius:8px;text-align:center;">
          <div style="font-size:11px;color:#6b7280;font-weight:600;">COM DESCARTE</div>
          <div style="font-size:20px;font-weight:800;color:#065f46;">R$ ${fmtDecimal(mc.media_com_descarte)}</div>
          <div style="font-size:10px;color:#065f46;">+R$ ${fmtDecimal(descarte.economia_mensal)}/mês</div>
        </div>
        <div style="background:#fef3c7;padding:12px;border-radius:8px;text-align:center;">
          <div style="font-size:11px;color:#6b7280;font-weight:600;">DESCARTADAS</div>
          <div style="font-size:20px;font-weight:800;color:#b45309;">${descarte.total_descartados}</div>
          <div style="font-size:10px;color:#92400e;">${descarte.fundamentacao || 'Art. 26 §6 EC 103'}</div>
        </div>`;
    }
    html += `</div>`;

    // Tabela de contribuições (mostrar primeiras 50 + resumo)
    const linhas = mc.linhas || [];
    const mostrar = linhas.slice(0, 60);
    const resto = linhas.length - 60;
    html += `<div style="overflow-x:auto;max-height:500px;overflow-y:auto;">
      <table class="tabela-planejamento" style="font-size:11px;">
        <thead style="position:sticky;top:0;"><tr>
          <th>Competência</th><th>Empregador</th><th>Sal. Original</th><th>Índice</th>
          <th>Sal. Corrigido</th><th>Teto</th><th>Status</th>
        </tr></thead>
        <tbody>`;
    mostrar.forEach(l => {
      const desc = l.descartado;
      const teto = l.limitado_teto;
      const bg = desc ? 'background:#fef2f2;opacity:0.7;text-decoration:line-through;' : teto ? 'background:#fef3c7;' : '';
      const status = desc ? '🗑️ Descartado' : teto ? '⚠️ Limitado ao teto' : '✅';
      html += `<tr style="${bg}">
        <td>${l.competencia}</td>
        <td style="max-width:150px;overflow:hidden;text-overflow:ellipsis;">${l.vinculo_nome || '—'}</td>
        <td style="text-align:right;">R$ ${fmtDecimal(l.salario_original)}</td>
        <td style="text-align:right;">${parseFloat(l.indice_correcao).toFixed(4)}</td>
        <td style="text-align:right;font-weight:600;">R$ ${fmtDecimal(l.salario_corrigido)}</td>
        <td style="text-align:right;color:#9ca3af;">R$ ${fmtDecimal(l.teto_vigente)}</td>
        <td style="text-align:center;">${status}</td>
      </tr>`;
    });
    if (resto > 0) {
      html += `<tr><td colspan="7" style="text-align:center;color:#9ca3af;padding:8px;">+ ${resto} contribuições omitidas</td></tr>`;
    }
    html += `</tbody></table></div></div>`;
  }

  // ── Botões de ação ────────────────────────────────────────────────────────
  const nomeCliente = coletarSegurado().dados_pessoais.nome || 'Cliente';
  html += `<div class="card">
    <h3 class="card-title">📁 Salvar e Exportar</h3>
    <p class="card-desc">Gere o relatório profissional completo ou salve o estudo como arquivo no seu computador.</p>
    <div class="actions-row">
      <button class="btn btn-secondary" onclick="copiarArgumentos()">📋 Copiar argumentos</button>
      <button class="btn btn-primary" onclick="gerarRelatorioPlanejamento()">📄 Relatório HTML</button>
      <button class="btn btn-primary" onclick="gerarRelatorioDocx()" style="background:#2563eb;">📝 Relatório Word (.docx)</button>
      <button class="btn btn-success" onclick="salvarEstudoCliente()">💾 Baixar Estudo (HTML)</button>
        <button class="btn btn-primary" onclick="salvarEstudoServidor()" style="background:#7c3aed;">💾 Salvar Estudo no Sistema</button>
    </div>
  </div>`;

  container.innerHTML = html;
}

window.copiarArgumentos = () => {
  if (!state.ultimoPlanejamento?.argumentos_cliente) return;
  const texto = state.ultimoPlanejamento.argumentos_cliente
    .map((a,i) => `${i+1}. ${a}`).join('\n\n');
  navigator.clipboard.writeText(texto).then(() => toast('Argumentos copiados!','success'));
};

window.gerarRelatorioPlanejamento = async () => {
  if (!state.ultimoPlanejamento) { toast('Calcule o planejamento primeiro','error'); return; }
  const seg = coletarSegurado();
  const advogado = document.getElementById('plan-advogado')?.value.trim() || '';
  const btn = event.target;
  btn.disabled = true; btn.textContent = 'Gerando...';
  try {
    const res = await fetch(`${API}/relatorio/planejamento/html`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ segurado: seg, planejamento: state.ultimoPlanejamento, nome_advogado: advogado }),
    });
    if (res.ok) {
      const html = await res.text();
      const blob = new Blob([html], {type:'text/html'});
      const janela = window.open(URL.createObjectURL(blob), '_blank');
      if (janela) janela.addEventListener('load', () => setTimeout(() => janela.print(), 800));
      toast('Relatório aberto! Use Ctrl+P para salvar como PDF.','success');
    } else {
      const err = await res.json();
      toast('Erro: '+(err.detail||'desconhecido'),'error');
    }
  } catch(e) { toast('Erro de conexão: '+e.message,'error'); }
  finally { btn.disabled=false; btn.textContent='📄 Relatório HTML'; }
};

window.gerarRelatorioDocx = async () => {
  if (!state.ultimoPlanejamento) { toast('Calcule o planejamento primeiro','error'); return; }
  const seg = coletarSegurado();
  const advogado = document.getElementById('plan-advogado')?.value.trim() || '';
  const btn = event.target;
  btn.disabled = true; btn.textContent = 'Gerando Word...';
  try {
    const res = await fetch(`${API}/relatorio/planejamento/docx`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ segurado: seg, planejamento: state.ultimoPlanejamento, nome_advogado: advogado }),
    });
    if (res.ok) {
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      const nomeCliente = (seg.dados_pessoais.nome || 'Cliente').replace(/\s+/g,'_');
      a.href = url;
      a.download = `Planejamento_${nomeCliente}.docx`;
      a.click();
      URL.revokeObjectURL(url);
      toast('Relatório Word gerado com sucesso!','success');
    } else {
      const err = await res.json();
      toast('Erro: '+(err.detail||'desconhecido'),'error');
    }
  } catch(e) { toast('Erro de conexão: '+e.message,'error'); }
  finally { btn.disabled=false; btn.textContent='📝 Relatório Word (.docx)'; }
};

window.salvarEstudoCliente = async () => {
  if (!state.ultimoPlanejamento) { toast('Calcule o planejamento primeiro','error'); return; }
  const seg = coletarSegurado();
  const advogado = document.getElementById('plan-advogado')?.value.trim() || '';
  const btn = event.target;
  btn.disabled = true; btn.textContent = 'Salvando...';
  try {
    const res = await fetch(`${API}/relatorio/planejamento/html`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ segurado: seg, planejamento: state.ultimoPlanejamento, nome_advogado: advogado }),
    });
    if (res.ok) {
      const html = await res.text();
      const blob = new Blob([html], {type:'text/html'});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      const nomeCliente = (seg.dados_pessoais.nome || 'Cliente').replace(/\s+/g,'_');
      const dataHoje = new Date().toLocaleDateString('pt-BR').replace(/\//g,'-');
      a.href = url;
      a.download = `Planejamento_${nomeCliente}_${dataHoje}.html`;
      a.click();
      URL.revokeObjectURL(url);
      toast('Estudo salvo! Verifique sua pasta de Downloads.','success');
    } else {
      const err = await res.json();
      toast('Erro: '+(err.detail||'desconhecido'),'error');
    }
  } catch(e) { toast('Erro de conexão: '+e.message,'error'); }
  finally { btn.disabled=false; btn.textContent='💾 Salvar Estudo (HTML)'; }
};

// ── APOSENTADORIA PcD ────────────────────────────────────────────────────
let pcdPeriodos = [];

window.adicionarPeriodoPcD = () => {
  const idx = pcdPeriodos.length;
  pcdPeriodos.push({ grau: '', data_inicio: '', data_fim: '' });
  renderizarPeriodosPcD();
};

window.removerPeriodoPcD = (idx) => {
  pcdPeriodos.splice(idx, 1);
  renderizarPeriodosPcD();
};

function renderizarPeriodosPcD() {
  const container = document.getElementById('pcd-periodos-lista');
  if (!container) return;
  if (pcdPeriodos.length === 0) {
    container.innerHTML = '<p style="color:#9ca3af;font-size:13px;">Nenhum periodo adicionado. Clique em "+ Adicionar Periodo".</p>';
    return;
  }
  let html = '';
  pcdPeriodos.forEach((p, i) => {
    html += `<div style="display:flex;gap:10px;align-items:center;margin-bottom:8px;padding:10px;background:#f8fafc;border-radius:8px;">
      <select onchange="pcdPeriodos[${i}].grau=this.value" style="flex:1;padding:6px 10px;border-radius:6px;border:1px solid #d1d5db;">
        <option value="" ${!p.grau?'selected':''}>Grau...</option>
        <option value="GRAVE" ${p.grau==='GRAVE'?'selected':''}>Grave</option>
        <option value="MODERADA" ${p.grau==='MODERADA'?'selected':''}>Moderada</option>
        <option value="LEVE" ${p.grau==='LEVE'?'selected':''}>Leve</option>
      </select>
      <input type="text" placeholder="Inicio DD/MM/AAAA" value="${p.data_inicio}" onchange="pcdPeriodos[${i}].data_inicio=this.value" style="flex:1;padding:6px 10px;border-radius:6px;border:1px solid #d1d5db;">
      <input type="text" placeholder="Fim DD/MM/AAAA (vazio=atual)" value="${p.data_fim}" onchange="pcdPeriodos[${i}].data_fim=this.value" style="flex:1;padding:6px 10px;border-radius:6px;border:1px solid #d1d5db;">
      <button onclick="removerPeriodoPcD(${i})" style="background:#fef2f2;color:#991b1b;border:none;padding:4px 10px;border-radius:6px;cursor:pointer;">X</button>
    </div>`;
  });
  container.innerHTML = html;
}

document.getElementById('btn-calcular-pcd')?.addEventListener('click', async () => {
  const seg = coletarSegurado();
  if (!seg.dados_pessoais.nome || !seg.dados_pessoais.data_nascimento) {
    toast('Preencha os dados do segurado primeiro','error'); return;
  }
  const grau = document.getElementById('pcd-grau').value;
  const der = document.getElementById('pcd-der').value.trim();
  if (!grau) { toast('Selecione o grau de deficiencia','error'); return; }
  if (!der) { toast('Informe a data de referencia','error'); return; }
  if (pcdPeriodos.length === 0) { toast('Adicione ao menos um periodo de deficiencia','error'); return; }

  const btn = document.getElementById('btn-calcular-pcd');
  btn.disabled = true; btn.innerHTML = '<span class="loader"></span> Calculando PcD...';

  try {
    const res = await fetch(`${API}/planejamento/pcd`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        segurado: seg, der, grau_deficiencia: grau,
        periodos_pcd: pcdPeriodos.filter(p => p.grau && p.data_inicio),
      }),
    });
    const data = await res.json();
    if (!res.ok) { toast(data.detail||'Erro','error'); return; }
    renderizarResultadoPcD(data);
  } catch (e) { toast('Erro de conexao: '+e.message,'error'); }
  finally { btn.disabled=false; btn.textContent='♿ Calcular Aposentadoria PcD'; }
});

function renderizarResultadoPcD(data) {
  const container = document.getElementById('resultado-pcd');
  if (!container) return;

  const elegiveis = (data.modalidades||[]).filter(m => m.elegivel);
  const melhor = data.melhor_opcao || {};

  let html = `<div class="card" style="border:2px solid #7c3aed;">
    <h3 class="card-title">♿ Resultado — Aposentadoria PcD (LC 142/2013)</h3>
    <p class="card-desc">Preservada pela EC 103/2019 (Art. 22). Nao aplicavel fator previdenciario (salvo se > 1.0).</p>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;margin-bottom:20px;">
      <div style="background:#f0f4ff;padding:12px;border-radius:8px;text-align:center;">
        <div style="font-size:11px;color:#6b7280;font-weight:600;">IDADE</div>
        <div style="font-size:22px;font-weight:800;color:#1a3c6e;">${data.idade} anos</div>
      </div>
      <div style="background:#f0f4ff;padding:12px;border-radius:8px;text-align:center;">
        <div style="font-size:11px;color:#6b7280;font-weight:600;">CARENCIA</div>
        <div style="font-size:22px;font-weight:800;color:${data.carencia_ok?'#065f46':'#991b1b'};">${data.carencia_meses} meses</div>
        <div style="font-size:10px;color:#9ca3af;">Exigido: ${data.carencia_exigida}</div>
      </div>
      <div style="background:#f0f4ff;padding:12px;border-radius:8px;text-align:center;">
        <div style="font-size:11px;color:#6b7280;font-weight:600;">SAL. BENEFICIO</div>
        <div style="font-size:18px;font-weight:800;color:#1a3c6e;">R$ ${fmtDecimal(data.salario_beneficio)}</div>
        <div style="font-size:10px;color:#9ca3af;">Media 80% maiores</div>
      </div>
    </div>`;

  // Tabela de modalidades
  html += `<div style="overflow-x:auto;">
    <table class="tabela-planejamento">
      <thead><tr>
        <th>Modalidade</th><th>Grau</th><th>Requisito</th><th>Situacao</th>
        <th>Elegivel?</th><th>RMI</th><th>Fundamentacao</th>
      </tr></thead>
      <tbody>`;
  (data.modalidades||[]).forEach(m => {
    const bg = m.elegivel ? 'background:#f0fdf4;' : '';
    const icon = m.elegivel ? '✅' : '❌';
    let req = '';
    if (m.tipo === 'TEMPO DE CONTRIBUIÇÃO') {
      req = m.tempo_exigido + '<br><small>' + (m.tempo_atual||'') + '</small>';
    } else {
      req = 'Idade: ' + (m.idade_exigida||'?') + ' anos<br>TC como PcD: ' + (m.tc_exigido_pcd||'15 anos');
    }
    let situacao = '';
    if (m.tipo === 'TEMPO DE CONTRIBUIÇÃO') {
      situacao = (m.cumprido ? '✅ TC cumprido' : '❌ TC faltante') + '<br>' + (m.carencia_ok ? '✅ Carencia OK' : '❌ Carencia insuficiente');
    } else {
      situacao = (m.idade_ok ? '✅ Idade OK' : '❌ Idade insuficiente') + '<br>' + (m.tc_pcd_ok ? '✅ TC PcD OK' : '❌ TC PcD insuficiente');
    }
    html += `<tr style="${bg}">
      <td><strong>${m.tipo}</strong></td>
      <td style="text-align:center;"><span style="background:#ede9fe;color:#7c3aed;padding:2px 8px;border-radius:4px;font-weight:700;font-size:12px;">${m.grau}</span></td>
      <td>${req}</td>
      <td style="font-size:12px;">${situacao}</td>
      <td style="text-align:center;font-size:20px;">${icon}</td>
      <td style="font-weight:700;color:${m.elegivel?'#065f46':'#991b1b'};">${m.rmi_formatada||'--'}</td>
      <td style="font-size:11px;color:#6b7280;">${m.base_legal||''}</td>
    </tr>`;
  });
  html += `</tbody></table></div>`;

  // Melhor opção
  if (melhor.tipo === 'PROJEÇÃO') {
    html += `<div style="margin-top:16px;padding:14px;background:#fef3c7;border-radius:8px;border-left:4px solid #b45309;">
      <div style="font-size:14px;font-weight:700;color:#92400e;">⏳ Ainda nao elegivel</div>
      <div style="font-size:13px;color:#374151;margin-top:4px;">${melhor.mensagem || 'Modalidade mais proxima: ' + (melhor.modalidade_mais_proxima||'') + ' — faltam ' + (melhor.faltam||'?')}</div>
    </div>`;
  } else if (melhor.rmi_formatada) {
    html += `<div style="margin-top:16px;padding:14px;background:#f0fdf4;border-radius:8px;border-left:4px solid #065f46;">
      <div style="font-size:14px;font-weight:700;color:#065f46;">✅ ELEGIVEL — Melhor opcao: ${melhor.tipo} (${melhor.grau})</div>
      <div style="font-size:22px;font-weight:800;color:#065f46;margin-top:4px;">${melhor.rmi_formatada}</div>
      <div style="font-size:12px;color:#374151;margin-top:4px;">${melhor.fundamentacao || ''}</div>
    </div>`;
  }

  // Tabela de conversão
  if (data.tabela_conversao?.length) {
    html += `<div style="margin-top:20px;">
      <h4 style="color:#1a3c6e;margin-bottom:8px;">Tabela de Fatores de Conversao (${data.sexo})</h4>
      <p style="font-size:12px;color:#6b7280;margin-bottom:8px;">Art. 5, LC 142/2013 — Conversao de tempo entre graus de deficiencia.</p>
      <div style="overflow-x:auto;">
      <table class="tabela-planejamento" style="font-size:11px;">
        <thead><tr><th>Origem</th><th>Destino</th><th>Fator</th><th>Tempo Origem</th><th>Tempo Destino</th></tr></thead>
        <tbody>`;
    data.tabela_conversao.forEach(t => {
      const bold = t.fator > 1 ? 'font-weight:700;color:#065f46;' : t.fator < 1 ? 'color:#991b1b;' : '';
      html += `<tr>
        <td>${t.origem}</td><td>${t.destino}</td>
        <td style="${bold}">${t.fator.toFixed(4)}</td>
        <td>${t.tempo_origem} anos</td><td>${t.tempo_destino} anos</td>
      </tr>`;
    });
    html += `</tbody></table></div></div>`;
  }

  html += `</div>`;
  container.innerHTML = html;
  container.classList.remove('hidden');
}

// ── Revisões ──────────────────────────────────────────────────────────────
// NOTA: Revisão da Vida Toda (Tema 1102 STF) ENCERRADA em 26/11/2025.
// ADIs 2.110 e 2.111 reverteram a tese. Não cabe mais ação.

document.getElementById('btn-teto').addEventListener('click', async () => {
  const dib=document.getElementById('teto-dib').value.trim();
  const rmi=document.getElementById('teto-rmi').value.replace(/\./g,'').replace(',','.');
  const sb=document.getElementById('teto-sb').value.replace(/\./g,'').replace(',','.');
  const der=document.getElementById('teto-der').value.trim();
  if (!dib||!rmi||!sb||!der) { toast('Preencha todos os campos','error'); return; }
  const btn=document.getElementById('btn-teto');
  btn.disabled=true; btn.textContent='Calculando...';
  try {
    const res = await fetch(`${API}/calculo/revisao/teto`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({dib, rmi_original:rmi, sb_original:sb, der_revisao:der}),
    });
    const data = await res.json();
    if (!res.ok) { toast(data.detail||'Erro','error'); return; }
    const aplicavel = data.ec20_aplicavel||data.ec41_aplicavel;
    document.getElementById('resultado-teto').innerHTML = `
      <div class="alert ${aplicavel?'alert-success':'alert-warning'}" style="margin-top:16px;">
        ${aplicavel?'✅ Revisão aplicável':'⚠️ Sem direito à revisão do teto'}</div>
      <div class="card"><div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:16px;">
        <div><div class="resumo-label">EC 20/98</div><div class="resumo-valor">${data.ec20_aplicavel?'✅':'❌'}</div>${data.rmi_pos_ec20?`<div>R$ ${fmtDecimal(data.rmi_pos_ec20)}</div>`:''}</div>
        <div><div class="resumo-label">EC 41/03</div><div class="resumo-valor">${data.ec41_aplicavel?'✅':'❌'}</div>${data.rmi_pos_ec41?`<div>R$ ${fmtDecimal(data.rmi_pos_ec41)}</div>`:''}</div>
        <div><div class="resumo-label">RMI Original</div><div class="resumo-valor">R$ ${fmtDecimal(data.rmi_original)}</div></div>
        <div><div class="resumo-label">RMI Revisada</div><div class="resumo-valor text-verde">R$ ${fmtDecimal(data.rmi_revisada)}</div></div>
        <div><div class="resumo-label">Diferença Mensal</div><div class="resumo-valor text-azul">R$ ${fmtDecimal(data.diferenca_mensal)}</div></div>
      </div></div>`;
    document.getElementById('resultado-teto').classList.remove('hidden');
  } catch { toast('Erro de conexão','error'); }
  finally { btn.disabled=false; btn.textContent='🔍 Calcular Revisão do Teto'; }
});

// ── Revisão Melhor Benefício ──────────────────────────────────────────────
document.getElementById('btn-rev-melhor').addEventListener('click', async () => {
  const der = document.getElementById('rev-mb-der').value.trim();
  const rmiInss = document.getElementById('rev-mb-rmi').value.replace(/\./g,'').replace(',','.');
  if (!der) { toast('Informe a DER do benefício','error'); return; }
  if (!rmiInss || parseFloat(rmiInss) <= 0) { toast('Informe a RMI concedida pelo INSS','error'); return; }
  const seg = coletarSegurado();
  if (!seg.dados_pessoais.nome) { toast('Importe o CNIS primeiro','error'); return; }

  const btn = document.getElementById('btn-rev-melhor');
  btn.disabled = true; btn.innerHTML = '<span class="loader"></span> Recalculando por todas as regras...';
  const resultEl = document.getElementById('resultado-rev-melhor');

  try {
    // Usar o endpoint de aposentadoria com tipo "transicao" para calcular todas as regras
    const res = await fetch(`${API}/calculo/aposentadoria`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ segurado: seg, der, tipo: 'transicao' }),
    });
    const data = await res.json();
    if (!res.ok) { toast(data.detail || 'Erro no cálculo', 'error'); return; }

    const rmiInssNum = parseFloat(rmiInss);
    const melhor = data.melhor_cenario;
    const melhorRmi = melhor ? parseFloat(melhor.rmi || 0) : 0;
    const diferenca = melhorRmi - rmiInssNum;
    const temRevisao = diferenca > 1; // diferença de pelo menos R$1

    let cenariosHtml = '';
    if (data.todos_cenarios?.length) {
      cenariosHtml = `<table style="width:100%;border-collapse:collapse;font-size:12px;margin-top:12px;">
        <thead><tr style="background:#f3f4f6;"><th style="padding:8px;text-align:left;">Regra</th><th style="padding:8px;text-align:center;">Elegível</th><th style="padding:8px;text-align:right;">RMI</th><th style="padding:8px;text-align:right;">vs INSS</th></tr></thead>
        <tbody>${data.todos_cenarios.map(c => {
          const rmiC = parseFloat(c.rmi || 0);
          const dif = rmiC - rmiInssNum;
          const cor = dif > 1 ? '#16a34a' : dif < -1 ? '#dc2626' : '#6b7280';
          return `<tr style="border-bottom:1px solid #e5e7eb;">
            <td style="padding:6px 8px;">${c.regra || c.nome || '—'}</td>
            <td style="padding:6px 8px;text-align:center;">${c.elegivel ? '<span style="color:#16a34a;font-weight:700;">Sim</span>' : '<span style="color:#9ca3af;">Não</span>'}</td>
            <td style="padding:6px 8px;text-align:right;font-weight:700;">${c.elegivel ? 'R$ ' + fmtDecimal(c.rmi) : '—'}</td>
            <td style="padding:6px 8px;text-align:right;color:${cor};font-weight:700;">${c.elegivel && rmiC > 0 ? (dif > 0 ? '+' : '') + 'R$ ' + fmtDecimal(dif.toFixed(2)) : '—'}</td>
          </tr>`;
        }).join('')}</tbody></table>`;
    }

    resultEl.innerHTML = `
      <div class="alert ${temRevisao ? 'alert-success' : 'alert-warning'}" style="margin-top:16px;">
        ${temRevisao
          ? `✅ <strong>REVISÃO FAVORÁVEL!</strong> O INSS concedeu R$ ${fmtDecimal(rmiInss)} mas o melhor benefício seria R$ ${fmtDecimal(melhor.rmi)} (${melhor.regra || melhor.nome || 'regra mais vantajosa'}) — diferença de <strong>R$ ${fmtDecimal(diferenca.toFixed(2))}/mês</strong>`
          : `⚠️ O INSS já concedeu pela melhor regra (R$ ${fmtDecimal(rmiInss)}). Nenhuma regra resulta em valor superior.`
        }
      </div>
      ${temRevisao ? `<div style="background:#f0fdf4;border-left:4px solid #16a34a;padding:12px 16px;border-radius:6px;margin-top:12px;">
        <div style="font-weight:700;color:#166534;">Fundamentação para Revisão</div>
        <div style="font-size:12px;color:#374151;margin-top:4px;">
          <strong>Art. 687, IN PRES/INSS 128/2022</strong>: "O INSS deve conceder o benefício mais vantajoso a que o segurado fizer jus, cabendo ao servidor orientar nesse sentido."<br>
          <strong>STF Tema 334 (RE 630.501/RS)</strong>: "O segurado do regime geral de previdência social tem direito adquirido a benefício calculado de modo mais vantajoso, sob a vigência de cada lei por ele alcançada."<br>
          <strong>Diferença mensal:</strong> R$ ${fmtDecimal(diferenca.toFixed(2))} | <strong>Diferença anual (c/ 13º):</strong> R$ ${fmtDecimal((diferenca * 13).toFixed(2))}
        </div>
      </div>` : ''}
      <div class="card" style="margin-top:12px;">
        <h3>Comparativo de Todas as Regras na DER ${der}</h3>
        ${cenariosHtml}
      </div>`;
    resultEl.classList.remove('hidden');
  } catch(err) { toast('Erro: ' + (err.message || 'conexão'), 'error'); }
  finally { btn.disabled = false; btn.innerHTML = '🔍 Verificar Melhor Benefício'; }
});

// ── Revisão Atividade Especial ───────────────────────────────────────────
// Mostrar vínculos especiais quando a aba é ativada
function renderizarVinculosEspeciaisRevisao() {
  const container = document.getElementById('rev-esp-vinculos-especiais');
  if (!container) return;
  const especiais = state.vinculos.filter(v => v.tipo_atividade && v.tipo_atividade !== 'NORMAL');
  if (!especiais.length) {
    container.innerHTML = `<div style="background:#fef3c7;padding:10px 14px;border-radius:8px;font-size:12px;color:#92400e;">
      <strong>Nenhum vínculo marcado como especial.</strong> Vá até a aba "Vínculos", edite os vínculos com exposição a agentes nocivos e mude o "Tipo de Atividade" para Especial 15, 20 ou 25 anos. Depois volte aqui para recalcular.
    </div>`;
    return;
  }
  const fatores = { ESPECIAL_15: { m: '2.33', f: '2.0' }, ESPECIAL_20: { m: '1.75', f: '1.5' }, ESPECIAL_25: { m: '1.4', f: '1.2' } };
  const sexo = document.getElementById('seg-sexo')?.value || 'MASCULINO';
  container.innerHTML = `<div style="background:#f0fdf4;padding:10px 14px;border-radius:8px;font-size:12px;">
    <strong style="color:#166534;">${especiais.length} vínculo(s) marcado(s) como especial:</strong>
    <table style="width:100%;margin-top:8px;font-size:11px;border-collapse:collapse;">
      <thead><tr style="background:#dcfce7;"><th style="padding:4px 8px;text-align:left;">Empregador</th><th>Período</th><th>Tipo</th><th>Fator (${sexo === 'FEMININO' ? 'F' : 'M'})</th></tr></thead>
      <tbody>${especiais.map(v => {
        const f = fatores[v.tipo_atividade] || {};
        const fator = sexo === 'FEMININO' ? (f.f || '1.0') : (f.m || '1.0');
        return `<tr style="border-bottom:1px solid #e5e7eb;">
          <td style="padding:4px 8px;">${v.empregador_nome || v.empregador_cnpj || '—'}</td>
          <td style="padding:4px 8px;text-align:center;">${v.data_inicio} a ${v.data_fim || 'presente'}</td>
          <td style="padding:4px 8px;text-align:center;">${v.tipo_atividade.replace('ESPECIAL_', 'Esp. ')} anos</td>
          <td style="padding:4px 8px;text-align:center;font-weight:700;color:#16a34a;">x${fator}</td>
        </tr>`;
      }).join('')}</tbody>
    </table>
  </div>`;
}

document.getElementById('btn-rev-especial').addEventListener('click', async () => {
  const der = document.getElementById('rev-esp-der').value.trim();
  if (!der) { toast('Informe a DER do benefício', 'error'); return; }
  const seg = coletarSegurado();
  if (!seg.dados_pessoais.nome) { toast('Importe o CNIS primeiro', 'error'); return; }

  // Verificar se tem vínculos especiais
  const especiais = seg.vinculos.filter(v => v.tipo_atividade && v.tipo_atividade !== 'NORMAL');
  if (!especiais.length) {
    toast('Marque pelo menos um vínculo como Especial na aba Vínculos', 'error');
    return;
  }

  const rmiInss = document.getElementById('rev-esp-rmi').value.replace(/\./g,'').replace(',','.');
  const btn = document.getElementById('btn-rev-especial');
  btn.disabled = true; btn.innerHTML = '<span class="loader"></span> Recalculando com conversão especial...';
  const resultEl = document.getElementById('resultado-rev-especial');

  try {
    // Calcular com os vínculos especiais marcados
    const res = await fetch(`${API}/calculo/aposentadoria`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ segurado: seg, der, tipo: 'transicao' }),
    });
    const data = await res.json();
    if (!res.ok) { toast(data.detail || 'Erro', 'error'); return; }

    // Também calcular o resumo para ver o TC com conversão
    const resResumo = await fetch(`${API}/calculo/resumo`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ segurado: seg, der, tipo: 'transicao' }),
    });
    const resumo = resResumo.ok ? await resResumo.json() : null;

    const melhor = data.melhor_cenario;
    const rmiEspecial = melhor ? parseFloat(melhor.rmi || 0) : 0;
    const rmiInssNum = rmiInss ? parseFloat(rmiInss) : 0;
    const diferenca = rmiInssNum > 0 ? rmiEspecial - rmiInssNum : 0;

    let tcHtml = '';
    if (resumo) {
      tcHtml = `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;margin-bottom:16px;">
        <div class="resumo-item"><div class="resumo-label">TC com Conversão</div><div class="resumo-valor text-azul">${resumo.tempo_contribuicao || '—'}</div></div>
        <div class="resumo-item"><div class="resumo-label">Dias Totais</div><div class="resumo-valor">${resumo.dias_total || '—'}</div></div>
        ${resumo.dias_especial_convertido ? `<div class="resumo-item"><div class="resumo-label">Dias Especiais (convertidos)</div><div class="resumo-valor text-verde">${resumo.dias_especial_convertido}</div></div>` : ''}
        <div class="resumo-item"><div class="resumo-label">Carência</div><div class="resumo-valor">${resumo.carencia || '—'}</div></div>
      </div>`;
    }

    resultEl.innerHTML = `
      ${rmiInssNum > 0 ? `<div class="alert ${diferenca > 1 ? 'alert-success' : 'alert-warning'}" style="margin-top:16px;">
        ${diferenca > 1
          ? `✅ <strong>REVISÃO FAVORÁVEL!</strong> Com o reconhecimento da atividade especial, a RMI seria R$ ${fmtDecimal(melhor.rmi)} — diferença de <strong>R$ ${fmtDecimal(diferenca.toFixed(2))}/mês</strong> (R$ ${fmtDecimal((diferenca * 13).toFixed(2))}/ano com 13º)`
          : `⚠️ Com a conversão especial, a RMI calculada (R$ ${fmtDecimal(melhor?.rmi || '0')}) não supera a concedida (R$ ${fmtDecimal(rmiInss)}).`
        }
      </div>` : ''}
      <div class="card" style="margin-top:12px;">
        <h3>Resultado com Conversão de Tempo Especial</h3>
        ${tcHtml}
        <div style="background:#eff6ff;padding:12px;border-radius:8px;margin-bottom:12px;">
          <div style="font-weight:700;color:#1e40af;">Melhor Cenário: ${melhor?.regra || melhor?.nome || '—'}</div>
          <div style="font-size:20px;font-weight:900;color:#16a34a;margin-top:4px;">RMI: R$ ${fmtDecimal(melhor?.rmi || '0')}</div>
        </div>
        <div style="font-size:12px;color:#374151;">
          <strong>Fundamentação:</strong> Art. 57 e 58 da Lei 8.213/91 — A aposentadoria especial será devida ao segurado que tiver trabalhado sujeito a condições especiais que prejudiquem a saúde ou a integridade física, durante 15, 20 ou 25 anos. O tempo de serviço exercido sob condições especiais poderá ser convertido em tempo de atividade comum (Art. 70, Decreto 3.048/99), aplicando-se o fator de conversão correspondente.
          ${diferenca > 1 ? `<br><br><strong>Valor dos atrasados estimado (5 anos):</strong> R$ ${fmtDecimal((diferenca * 60 * 1.15).toFixed(2))} (estimativa c/ correção)` : ''}
        </div>
      </div>`;
    resultEl.classList.remove('hidden');
  } catch(err) { toast('Erro: ' + (err.message || 'conexão'), 'error'); }
  finally { btn.disabled = false; btn.innerHTML = '⚡ Recalcular com Atividade Especial'; }
});

// Observar troca de aba para renderizar vínculos especiais
document.querySelectorAll('.tabs .tab[data-tab="especial-revisao"]').forEach(tab => {
  tab.addEventListener('click', () => renderizarVinculosEspeciaisRevisao());
});

// ── Atrasados ─────────────────────────────────────────────────────────────
document.getElementById('btn-atrasados').addEventListener('click', async () => {
  const dib=document.getElementById('at-dib').value.trim();
  const rmi=limparValorMonetario(document.getElementById('at-rmi').value);
  const rmiPagaEl=document.getElementById('at-rmi-paga');
  const rmiPaga=rmiPagaEl ? limparValorMonetario(rmiPagaEl.value) : '';
  const atu=document.getElementById('at-atualizacao').value.trim();
  const aju=document.getElementById('at-ajuizamento').value.trim();
  if (!dib||!rmi||!atu) { toast('Preencha DIB, RMI e data de atualização','error'); return; }
  const btn=document.getElementById('btn-atrasados');
  btn.disabled=true; btn.innerHTML='<span class="loader"></span> Calculando...';
  try {
    const payload = { dib, rmi_original:rmi, data_atualizacao:atu,
      data_ajuizamento:aju||null, incluir_juros:document.getElementById('at-juros').checked };
    if (rmiPaga && parseFloat(rmiPaga) > 0) payload.rmi_paga = rmiPaga;
    const res = await fetch(`${API}/calculo/atrasados`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) { toast(data.detail||'Erro','error'); return; }
    const primeiras = data.parcelas.slice(0,50);
    const resto = data.parcelas.length - 50;
    const isDiferenca = data.tipo_calculo === 'diferenca';
    let explicacaoHtml = '';
    if (isDiferenca) {
      explicacaoHtml = `<div style="background:#f0fdf4;border-left:4px solid #22c55e;padding:12px 16px;border-radius:6px;margin-bottom:16px;">
        <div style="font-size:13px;font-weight:700;color:#166534;">Calculo sobre a DIFERENCA</div>
        <div style="font-size:12px;color:#374151;margin-top:4px;">
          RMI correta: <strong>R$ ${fmtDecimal(data.rmi_correta)}</strong> |
          RMI paga pelo INSS: <strong>R$ ${fmtDecimal(data.rmi_paga)}</strong> |
          Diferenca mensal: <strong style="color:#dc2626;">R$ ${fmtDecimal(data.diferenca_mensal)}</strong>
        </div>
        <div style="font-size:11px;color:#6b7280;margin-top:4px;">${data.explicacao || ''}</div>
      </div>`;
    }
    document.getElementById('resultado-atrasados').innerHTML = `
      <div class="card" style="margin-top:16px;">
        ${explicacaoHtml}
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:16px;margin-bottom:20px;">
          <div class="resumo-item"><div class="resumo-label">Competencias</div><div class="resumo-valor">${data.parcelas_calculadas}</div></div>
          <div class="resumo-item"><div class="resumo-label">Prescritas</div><div class="resumo-valor">${data.parcelas_prescritas}</div></div>
          ${isDiferenca ? `<div class="resumo-item"><div class="resumo-label">Diferenca/mes</div><div class="resumo-valor text-azul">R$ ${fmtDecimal(data.diferenca_mensal)}</div></div>` : ''}
          <div class="resumo-item"><div class="resumo-label">Total Principal</div><div class="resumo-valor">R$ ${fmtDecimal(data.total_principal)}</div></div>
          <div class="resumo-item"><div class="resumo-label">Total Juros</div><div class="resumo-valor">R$ ${fmtDecimal(data.total_juros)}</div></div>
          <div class="resumo-item"><div class="resumo-label">TOTAL GERAL</div><div class="resumo-valor text-verde" style="font-size:26px;">R$ ${fmtDecimal(data.total_geral)}</div></div>
        </div>
        <table class="parcelas-table">
          <thead><tr><th>Competencia</th><th>${isDiferenca ? 'Diferenca Base' : 'Valor Base'}</th><th>Fator</th><th>Corrigido</th><th>Juros</th><th>Total</th></tr></thead>
          <tbody>
            ${primeiras.map(p=>`<tr><td>${p.competencia}</td><td>R$ ${fmtDecimal(p.valor_base)}</td><td>${parseFloat(p.fator_correcao).toFixed(6)}</td><td>R$ ${fmtDecimal(p.valor_corrigido)}</td><td>R$ ${fmtDecimal(p.juros)}</td><td><strong>R$ ${fmtDecimal(p.total_parcela)}</strong></td></tr>`).join('')}
            ${resto>0?`<tr><td colspan="6" style="text-align:center;color:#9ca3af">+ ${resto} parcelas omitidas</td></tr>`:''}
            <tr class="total-row"><td colspan="3"><strong>TOTAIS</strong></td><td><strong>R$ ${fmtDecimal(data.total_principal)}</strong></td><td><strong>R$ ${fmtDecimal(data.total_juros)}</strong></td><td><strong>R$ ${fmtDecimal(data.total_geral)}</strong></td></tr>
          </tbody>
        </table>
      </div>`;
    document.getElementById('resultado-atrasados').classList.remove('hidden');
  } catch { toast('Erro de conexão','error'); }
  finally { btn.disabled=false; btn.textContent='💰 Calcular Atrasados'; }
});

// ── Relatório ─────────────────────────────────────────────────────────────
document.getElementById('btn-gerar-relatorio').addEventListener('click', async () => {
  if (!state.ultimoCalculo) { toast('Faça um cálculo antes de gerar o relatório','error'); return; }
  const btn = document.getElementById('btn-gerar-relatorio');
  btn.disabled=true; btn.innerHTML='<span class="loader"></span> Gerando...';
  try {
    const res = await fetch(`${API}/relatorio/html`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ segurado:coletarSegurado(), calculo:state.ultimoCalculo }),
    });
    if (res.ok) {
      const html = await res.text();
      const blob = new Blob([html], {type:'text/html'});
      const janela = window.open(URL.createObjectURL(blob), '_blank');
      if (janela) janela.addEventListener('load', () => setTimeout(()=>janela.print(),500));
      toast('Relatório aberto! Use Ctrl+P → Salvar como PDF.','success');
    } else { const e=await res.json(); toast(e.detail||'Erro','error'); }
  } catch { toast('Erro','error'); }
  finally { btn.disabled=false; btn.textContent='📋 Gerar Relatório (PDF)'; }
});

document.getElementById('btn-exportar-json').addEventListener('click', () => {
  if (!state.ultimoCalculo) { toast('Faça um cálculo primeiro','error'); return; }
  const json = JSON.stringify({ segurado:coletarSegurado(), calculo:state.ultimoCalculo, gerado_em:new Date().toISOString() }, null, 2);
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([json], {type:'application/json'}));
  a.download = `calculo_${new Date().toISOString().slice(0,10)}.json`;
  a.click();
  toast('JSON exportado!','success');
});

// ── APOSENTADORIA PcD (LC 142/2013) ─────────────────────────────────────
// pcdPeriodos já declarado acima (linha ~1207)

window.adicionarPeriodoPcD = () => {
  pcdPeriodos.push({ grau: 'MODERADA', data_inicio: '', data_fim: '' });
  renderPeriodosPcD();
};

window.removerPeriodoPcD = (idx) => {
  pcdPeriodos.splice(idx, 1);
  renderPeriodosPcD();
};

function renderPeriodosPcD() {
  const container = document.getElementById('pcd-periodos-lista');
  if (!container) return;
  if (!pcdPeriodos.length) {
    container.innerHTML = '<p style="color:#9ca3af;font-size:13px;">Nenhum período adicionado. Clique em "+ Adicionar Período".</p>';
    return;
  }
  let html = '';
  pcdPeriodos.forEach((p, i) => {
    html += `<div style="display:flex;gap:10px;align-items:center;margin-bottom:8px;padding:10px;background:#f8fafc;border-radius:8px;">
      <select onchange="pcdPeriodos[${i}].grau=this.value" style="flex:1;">
        <option value="GRAVE" ${p.grau==='GRAVE'?'selected':''}>Grave</option>
        <option value="MODERADA" ${p.grau==='MODERADA'?'selected':''}>Moderada</option>
        <option value="LEVE" ${p.grau==='LEVE'?'selected':''}>Leve</option>
      </select>
      <input type="text" placeholder="Início DD/MM/AAAA" value="${p.data_inicio}" onchange="pcdPeriodos[${i}].data_inicio=this.value" style="flex:1;">
      <input type="text" placeholder="Fim DD/MM/AAAA (vazio=atual)" value="${p.data_fim}" onchange="pcdPeriodos[${i}].data_fim=this.value" style="flex:1;">
      <button class="btn" style="padding:4px 10px;background:#fef2f2;color:#991b1b;" onclick="removerPeriodoPcD(${i})">✕</button>
    </div>`;
  });
  container.innerHTML = html;
}

document.getElementById('btn-calcular-pcd')?.addEventListener('click', async () => {
  const seg = coletarSegurado();
  if (!seg.dados_pessoais.nome || !seg.dados_pessoais.data_nascimento) {
    toast('Preencha os dados do segurado primeiro', 'error'); return;
  }
  const grau = document.getElementById('pcd-grau').value;
  if (!grau) { toast('Selecione o grau de deficiência', 'error'); return; }
  const der = document.getElementById('pcd-der').value.trim();
  if (!der) { toast('Informe a data de referência', 'error'); return; }
  if (!pcdPeriodos.length || !pcdPeriodos[0].data_inicio) {
    toast('Adicione pelo menos um período com deficiência', 'error'); return;
  }

  const btn = document.getElementById('btn-calcular-pcd');
  btn.disabled = true; btn.innerHTML = '<span class="loader"></span> Calculando PcD...';

  try {
    const res = await fetch(`${API}/planejamento/pcd`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        segurado: seg, der, grau_deficiencia: grau,
        periodos_pcd: pcdPeriodos.map(p => ({
          grau: p.grau, data_inicio: p.data_inicio, data_fim: p.data_fim || null,
        })),
      }),
    });
    const data = await res.json();
    if (!res.ok) { toast(data.detail || 'Erro', 'error'); return; }
    renderizarPcD(data);
  } catch (e) { toast('Erro de conexão: ' + e.message, 'error'); }
  finally { btn.disabled = false; btn.textContent = '♿ Calcular Aposentadoria PcD'; }
});

function renderizarPcD(data) {
  const container = document.getElementById('resultado-pcd');
  const sb = data.salario_beneficio ? `R$ ${fmtDecimal(data.salario_beneficio)}` : '—';

  let html = `
  <div class="card" style="border-left:4px solid #7c3aed;">
    <h3 class="card-title">♿ Resultado — Aposentadoria PcD (LC 142/2013)</h3>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;margin-bottom:16px;">
      <div style="background:#ede9fe;padding:12px;border-radius:8px;text-align:center;">
        <div style="font-size:11px;color:#6b7280;">IDADE</div>
        <div style="font-size:22px;font-weight:800;color:#7c3aed;">${data.idade || '—'} anos</div>
      </div>
      <div style="background:#ede9fe;padding:12px;border-radius:8px;text-align:center;">
        <div style="font-size:11px;color:#6b7280;">CARÊNCIA</div>
        <div style="font-size:22px;font-weight:800;color:${data.carencia_ok ? '#065f46' : '#991b1b'};">${data.carencia_meses || 0} meses</div>
        <div style="font-size:10px;">${data.carencia_ok ? '✅ OK' : '❌ Faltam ' + (180 - (data.carencia_meses||0))}</div>
      </div>
      <div style="background:#ede9fe;padding:12px;border-radius:8px;text-align:center;">
        <div style="font-size:11px;color:#6b7280;">SALÁRIO BENEFÍCIO</div>
        <div style="font-size:18px;font-weight:800;color:#7c3aed;">${sb}</div>
        <div style="font-size:10px;color:#9ca3af;">Média 80% maiores</div>
      </div>
    </div>`;

  // Melhor opção
  if (data.melhor_opcao) {
    const mo = data.melhor_opcao;
    if (mo.rmi) {
      html += `<div style="background:#f0fdf4;padding:16px;border-radius:8px;border-left:4px solid #065f46;margin-bottom:16px;">
        <div style="font-size:15px;font-weight:800;color:#065f46;">✅ ELEGÍVEL — ${mo.tipo} (Grau ${mo.grau})</div>
        <div style="font-size:24px;font-weight:900;color:#065f46;margin-top:4px;">${mo.rmi_formatada}</div>
        <div style="font-size:12px;color:#374151;margin-top:4px;">${mo.fundamentacao || ''}</div>
      </div>`;
    } else if (mo.mensagem) {
      html += `<div style="background:#fef3c7;padding:16px;border-radius:8px;border-left:4px solid #b45309;margin-bottom:16px;">
        <div style="font-size:14px;font-weight:700;color:#b45309;">⏳ ${mo.mensagem}</div>
      </div>`;
    }
  }

  // Modalidades
  html += `<h4 style="color:#1a3c6e;margin-bottom:8px;">Modalidades Analisadas</h4>
    <div style="overflow-x:auto;">
    <table class="tabela-planejamento">
      <thead><tr><th>Modalidade</th><th>Grau</th><th>Exigido</th><th>Atual</th><th>Elegível?</th><th>RMI</th><th>Base Legal</th></tr></thead>
      <tbody>`;
  (data.modalidades || []).forEach(m => {
    const bg = m.elegivel ? 'background:#f0fdf4;' : '';
    html += `<tr style="${bg}">
      <td><strong>${m.tipo}</strong></td>
      <td>${m.grau}</td>
      <td>${m.tipo === 'IDADE' ? m.idade_exigida + ' anos' : m.tempo_exigido}</td>
      <td>${m.tipo === 'IDADE' ? m.idade_atual + ' anos' : m.tempo_atual}</td>
      <td style="text-align:center;font-size:18px;">${m.elegivel ? '✅' : '❌'}</td>
      <td style="font-weight:700;color:${m.elegivel ? '#065f46' : '#991b1b'};">${m.rmi_formatada || '—'}</td>
      <td style="font-size:11px;">${m.base_legal || ''}</td>
    </tr>`;
  });
  html += `</tbody></table></div>`;

  // Tabela de conversão
  if (data.tabela_conversao?.length) {
    html += `<h4 style="color:#1a3c6e;margin-top:16px;margin-bottom:8px;">Tabela de Fatores de Conversão (${data.sexo || ''})</h4>
      <div style="overflow-x:auto;">
      <table class="tabela-planejamento" style="font-size:11px;">
        <thead><tr><th>De (Origem)</th><th>Para (Destino)</th><th>Fator</th><th>Tempo Origem</th><th>Tempo Destino</th></tr></thead>
        <tbody>`;
    data.tabela_conversao.forEach(t => {
      html += `<tr>
        <td>${t.origem}</td><td>${t.destino}</td>
        <td style="font-weight:700;">${t.fator}</td>
        <td>${t.tempo_origem} anos</td><td>${t.tempo_destino} anos</td>
      </tr>`;
    });
    html += `</tbody></table></div>`;
  }

  html += `</div>`;
  container.innerHTML = html;
  container.classList.remove('hidden');
}

// ── Utilitários ───────────────────────────────────────────────────────────
function limparValorMonetario(v) {
  // Remove R$, espacos, e converte formato brasileiro para numero
  // Aceita: "R$ 3.092,59", "3.092,59", "3092.59", "R$ 3.092.59", "3092,59"
  let s = String(v).replace(/[R$\s]/g,'').trim();
  if (!s) return '';
  // Se tem virgula, é formato brasileiro (ponto=milhar, virgula=decimal)
  if (s.includes(',')) {
    s = s.replace(/\./g,'').replace(',','.');
  } else {
    // Sem virgula: se tem mais de 1 ponto, os primeiros sao milhar
    const pontos = (s.match(/\./g)||[]).length;
    if (pontos > 1) {
      // Ex: "3.092.59" -> ultimo ponto e decimal, anteriores sao milhar
      const idx = s.lastIndexOf('.');
      s = s.substring(0, idx).replace(/\./g,'') + '.' + s.substring(idx + 1);
    }
    // Se tem 1 ponto: ja e formato decimal americano, ok
  }
  return s;
}

function fmtDecimal(v) {
  if (!v && v !== 0) return '0,00';
  const n = parseFloat(v);
  if (isNaN(n)) return String(v);
  return n.toLocaleString('pt-BR', { minimumFractionDigits:2, maximumFractionDigits:2 });
}

function fmtCPF(v) {
  const d = String(v).replace(/\D/g,'');
  return d.length===11 ? `${d.slice(0,3)}.${d.slice(3,6)}.${d.slice(6,9)}-${d.slice(9)}` : v;
}

function fmtCNPJ(v) {
  const d = String(v).replace(/\D/g,'');
  return d.length===14 ? `${d.slice(0,2)}.${d.slice(2,5)}.${d.slice(5,8)}/${d.slice(8,12)}-${d.slice(12)}` : v;
}

function toast(msg, tipo='info', duracao=4500) {
  const el = document.createElement('div');
  el.className = `toast ${tipo}`;
  el.textContent = msg;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => el.remove(), duracao);
}

// Máscara de data automática
document.addEventListener('input', e => {
  if (e.target.placeholder?.includes('DD/MM/AAAA')) {
    let v = e.target.value.replace(/\D/g,'');
    if (v.length>=3) v = v.slice(0,2)+'/'+v.slice(2);
    if (v.length>=6) v = v.slice(0,5)+'/'+v.slice(5);
    e.target.value = v.slice(0,10);
  }
});

// ── Estudos Salvos ──────────────────────────────────────────────────────
window.carregarEstudos = async () => {
  const container = document.getElementById('lista-estudos');
  if (!container) return;
  container.innerHTML = '<p style="color:#9ca3af;text-align:center;padding:16px;">Carregando...</p>';
  try {
    const res = await fetch(`${API}/estudos/listar`);
    const estudos = await res.json();
    if (!estudos.length) {
      container.innerHTML = '<p style="color:#9ca3af;text-align:center;padding:32px;">Nenhum estudo salvo ainda. Calcule um planejamento e clique em "Salvar Estudo".</p>';
      return;
    }
    let html = `<table class="tabela-planejamento">
      <thead><tr><th>Cliente</th><th>Data</th><th>Melhor Regra</th><th>RMI</th><th>Ações</th></tr></thead>
      <tbody>`;
    estudos.forEach(e => {
      html += `<tr>
        <td><strong>${e.nome_cliente}</strong></td>
        <td>${e.data_elaboracao}</td>
        <td>${e.regra_melhor || '—'}</td>
        <td>${e.rmi_melhor || '—'}</td>
        <td>
          <button class="btn btn-secondary" style="padding:4px 10px;font-size:12px;" onclick="abrirEstudo('${e.id}')">📂 Abrir</button>
          <button class="btn" style="padding:4px 10px;font-size:12px;background:#fef2f2;color:#991b1b;" onclick="deletarEstudo('${e.id}','${e.nome_cliente}')">🗑️</button>
        </td>
      </tr>`;
    });
    html += '</tbody></table>';
    container.innerHTML = html;
  } catch (e) {
    container.innerHTML = '<p style="color:#991b1b;text-align:center;">Erro ao carregar estudos.</p>';
  }
};

window.abrirEstudo = async (id) => {
  try {
    const res = await fetch(`${API}/estudos/${id}`);
    if (!res.ok) { toast('Estudo não encontrado','error'); return; }
    const estudo = await res.json();

    // Preencher dados do segurado
    if (estudo.segurado) {
      preencherFormularioSegurado(estudo.segurado);
      state.vinculos = estudo.segurado.vinculos || [];
      renderizarVinculos();
    }

    // Mostrar planejamento
    if (estudo.planejamento) {
      state.ultimoPlanejamento = estudo.planejamento;
      // Navegar para a aba de planejamento
      document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
      document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
      document.querySelector('[data-page="planejamento"]').classList.add('active');
      document.getElementById('page-planejamento').classList.add('active');

      const resultEl = document.getElementById('resultado-planejamento');
      renderizarPlanejamento(estudo.planejamento, resultEl);
      resultEl.classList.remove('hidden');
    }

    if (estudo.nome_advogado) {
      const adv = document.getElementById('plan-advogado');
      if (adv) adv.value = estudo.nome_advogado;
    }

    toast(`Estudo de ${estudo.nome_cliente} carregado!`, 'success');
  } catch(e) { toast('Erro ao abrir estudo: ' + e.message, 'error'); }
};

window.deletarEstudo = async (id, nome) => {
  if (!confirm(`Deseja realmente excluir o estudo de ${nome}?`)) return;
  try {
    const res = await fetch(`${API}/estudos/${id}`, { method: 'DELETE' });
    if (res.ok) {
      toast('Estudo excluído!', 'success');
      carregarEstudos();
    } else {
      toast('Erro ao excluir', 'error');
    }
  } catch(e) { toast('Erro: ' + e.message, 'error'); }
};

window.salvarEstudoServidor = async () => {
  if (!state.ultimoPlanejamento) { toast('Calcule o planejamento primeiro','error'); return; }
  const seg = coletarSegurado();
  const advogado = document.getElementById('plan-advogado')?.value.trim() || '';
  const btn = event.target;
  btn.disabled = true; btn.textContent = 'Salvando...';
  try {
    const res = await fetch(`${API}/estudos/salvar`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        segurado: seg,
        planejamento: state.ultimoPlanejamento,
        nome_advogado: advogado,
        observacoes: '',
      }),
    });
    if (res.ok) {
      const data = await res.json();
      toast(`Estudo de ${data.nome_cliente} salvo com sucesso!`, 'success');
    } else {
      const err = await res.json();
      toast('Erro: ' + (err.detail || 'desconhecido'), 'error');
    }
  } catch(e) { toast('Erro: ' + e.message, 'error'); }
  finally { btn.disabled = false; btn.textContent = '💾 Salvar Estudo no Sistema'; }
};

// Auto-carregar estudos quando navegar para a aba
document.querySelector('[data-page="estudos"]')?.addEventListener('click', () => {
  setTimeout(carregarEstudos, 100);
});
