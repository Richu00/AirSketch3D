import { BrowserRouter,Routes,Route } from 'react-router-dom'; import { useWebSocket } from './hooks/useWebSocket'; import { useKeyboard } from './hooks/useKeyboard'; import { Dashboard } from './pages/Dashboard';
function Inner(){useWebSocket();useKeyboard();return <Routes><Route path="*" element={<Dashboard/>}/></Routes>}; export function App(){return <BrowserRouter><Inner/></BrowserRouter>}
