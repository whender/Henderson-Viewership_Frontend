const DEFAULT_LOCAL_BACKEND = "http://localhost:8000";
const DEFAULT_PROD_BACKEND = "https://henderson-viewership-backend.onrender.com";

const BACKEND_BASE =
  process.env.REACT_APP_BACKEND_BASE ||
  (window.location.hostname === "localhost"
    ? DEFAULT_LOCAL_BACKEND
    : DEFAULT_PROD_BACKEND);

export default BACKEND_BASE;
