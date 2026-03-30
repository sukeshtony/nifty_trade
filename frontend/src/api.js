import axios from 'axios';

const API_BASE = '/api';

const api = axios.create({
  baseURL: API_BASE,
  timeout: 10000,
});

// ── Market ──

export const fetchNiftyPrice = async () => {
  const { data } = await api.get('/market/nifty-price');
  return data;
};

export const fetchMarketOverview = async () => {
  const { data } = await api.get('/market/overview');
  return data;
};

// ── Signals ──

export const fetchCurrentSignal = async () => {
  const { data } = await api.get('/signals/current');
  return data;
};

export const fetchSignalHistory = async (limit = 20) => {
  const { data } = await api.get(`/signals/history?limit=${limit}`);
  return data;
};

// ── Options ──

export const fetchOptionsAnalysis = async () => {
  const { data } = await api.get('/options/analysis');
  return data;
};

// ── Trades ──

export const createTrade = async (tradeData) => {
  const { data } = await api.post('/trades', tradeData);
  return data;
};

export const closeTrade = async (tradeId, exitPrice) => {
  const { data } = await api.put(`/trades/${tradeId}/close`, { exit_price: exitPrice });
  return data;
};

export const fetchActiveTrades = async () => {
  const { data } = await api.get('/trades/active');
  return data;
};

export const fetchTradeHistory = async (limit = 50) => {
  const { data } = await api.get(`/trades/history?limit=${limit}`);
  return data;
};

export const fetchTradeSummary = async () => {
  const { data } = await api.get('/trades/summary');
  return data;
};

// ── Paper Trading ──

export const initPaperAccount = async (balance) => {
  const { data } = await api.post('/paper/account/init', { balance });
  return data;
};

export const fetchPaperAccount = async () => {
  const { data } = await api.get('/paper/account');
  return data;
};

export const placePaperTrade = async (tradeData) => {
  const { data } = await api.post('/paper/trade/place', tradeData);
  return data;
};

export const closePaperTrade = async (tradeId, exitPrice) => {
  const { data } = await api.post(`/paper/trade/close/${tradeId}`, { exit_price: exitPrice });
  return data;
};

export const fetchPaperOptionChain = async () => {
  const { data } = await api.get('/paper/option-chain');
  return data;
};

export const fetchActivePaperTrades = async () => {
  const { data } = await api.get('/paper/trades/active');
  return data;
};

export const fetchPaperTradeHistory = async () => {
  const { data } = await api.get('/paper/trades/history');
  return data;
};

export default api;
