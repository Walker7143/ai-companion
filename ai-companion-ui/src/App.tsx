import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout';
import { ToastContainer } from './components/ui';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Dashboard } from './pages/Dashboard';
import { Session } from './pages/Session';
import { Logs } from './pages/Logs';
import { Memory } from './pages/Memory';
import { Understanding } from './pages/Understanding';
import { StyleLab } from './pages/StyleLab';
import { Operations } from './pages/Operations';
import { Debug } from './pages/Debug';
import { Settings } from './pages/Settings';

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/session" element={<Session />} />
            <Route path="/logs" element={<Logs />} />
            <Route path="/memory" element={<Memory />} />
            <Route path="/understanding" element={<Understanding />} />
            <Route path="/style" element={<StyleLab />} />
            <Route path="/operations" element={<Operations />} />
            <Route path="/debug" element={<Debug />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </ErrorBoundary>
      </Layout>
      <ToastContainer />
    </BrowserRouter>
  );
}

export default App;
