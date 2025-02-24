import sqlite3
import yfinance as yf
import csv
import matplotlib.pyplot as plt  # For visualization

class DatabaseManager:
    def __init__(self, db_name="portfolio.db"):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        """Creates the required tables if they do not exist."""
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                                id INTEGER PRIMARY KEY, 
                                name TEXT UNIQUE)''')

        self.cursor.execute('''CREATE TABLE IF NOT EXISTS portfolios (
                                id INTEGER PRIMARY KEY, 
                                owner_id INTEGER UNIQUE, 
                                name TEXT, 
                                FOREIGN KEY(owner_id) REFERENCES users(id))
                            ''')

        self.cursor.execute('''CREATE TABLE IF NOT EXISTS assets (
                                id INTEGER PRIMARY KEY, 
                                portfolio_id INTEGER, 
                                ticker TEXT, 
                                name TEXT, 
                                purchase_price REAL, 
                                quantity INTEGER,
                                market_price REAL,  
                                pnl REAL,  
                                order_type TEXT, 
                                limit_price REAL, 
                                FOREIGN KEY(portfolio_id) REFERENCES portfolios(id))
                            ''')
        self.conn.commit()

    def register_user(self, name):
        try:
            self.cursor.execute("INSERT INTO users (name) VALUES (?)", (name,))
            self.conn.commit()
            return self.cursor.lastrowid
        except sqlite3.IntegrityError:
            print("User already exists. Please log in.")
            return None

    def login_user(self, name):
        self.cursor.execute("SELECT id FROM users WHERE name = ?", (name,))
        user = self.cursor.fetchone()
        return user[0] if user else None

    def insert_portfolio(self, owner_id, name):
        self.cursor.execute("INSERT INTO portfolios (owner_id, name) VALUES (?, ?)", (owner_id, name))
        self.conn.commit()
        return self.cursor.lastrowid

    def get_market_price(self, ticker):
        """Fetch the latest market price from Yahoo Finance."""
        try:
            stock = yf.Ticker(ticker)
            stock_data = stock.history(period="1d")
            if not stock_data.empty:
                return stock_data["Close"].iloc[-1]
            else:
                return None
        except Exception as e:
            print(f"Error fetching market data for {ticker}: {e}")
            return None

    def insert_asset(self, portfolio_id, ticker, name, purchase_price, quantity, order_type, limit_price=None):
        """Adds a stock to the portfolio with real-time market price and calculates P&L."""
        if order_type == 'market':
            market_price = self.get_market_price(ticker)
            if market_price is None:
                print("Error fetching market price. Stock not added.")
                return None
            purchase_price = market_price  # Use market price for purchase
        elif order_type == 'limit' and limit_price is not None:
            market_price = limit_price  # Use the provided limit price for purchase
        else:
            print("Invalid order type or missing limit price.")
            return None

        pnl = (market_price - purchase_price) * quantity

        self.cursor.execute(""" 
            INSERT INTO assets (portfolio_id, ticker, name, purchase_price, quantity, market_price, pnl, order_type, limit_price) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (portfolio_id, ticker, name, purchase_price, quantity, market_price, pnl, order_type, limit_price))

        self.conn.commit()
        return self.cursor.lastrowid

    def check_portfolio(self, portfolio_id):
        """Displays all assets in a portfolio and updates P&L in real-time."""
        self.cursor.execute("SELECT id, ticker, name, purchase_price, quantity FROM assets WHERE portfolio_id = ?",
                            (portfolio_id,))
        assets = self.cursor.fetchall()
        if not assets:
            print("\nNo assets found in this portfolio.")
            return []

        updated_assets = []
        for asset in assets:
            asset_id, ticker, name, purchase_price, quantity = asset
            market_price = self.get_market_price(ticker)
            if market_price is None:
                print(f"Could not retrieve market price for {ticker}.")
                continue

            pnl = (market_price - purchase_price) * quantity
            updated_assets.append((asset_id, ticker, name, purchase_price, market_price, quantity, pnl))

            self.cursor.execute("UPDATE assets SET market_price = ?, pnl = ? WHERE id = ?",
                                (market_price, pnl, asset_id))
        self.conn.commit()

        return updated_assets

    def update_asset(self, portfolio_id, ticker, purchase_price, quantity, order_type):
        """Updates the stock's record in the portfolio with the new purchase price and quantity."""
        self.cursor.execute("SELECT id, purchase_price, quantity FROM assets WHERE portfolio_id = ? AND ticker = ?",
                            (portfolio_id, ticker))
        asset = self.cursor.fetchone()

        if asset:
            asset_id, current_purchase_price, current_quantity = asset
            new_quantity = current_quantity + quantity  # Update the quantity

            if order_type == 'market':
                purchase_price = current_purchase_price  # If it's a market order, the price stays the same

            if new_quantity == 0:
                self.remove_asset(asset_id)
                print(f"Removed {ticker} from the portfolio.")
            else:
                self.cursor.execute("""
                    UPDATE assets
                    SET purchase_price = ?, quantity = ?
                    WHERE id = ?
                """, (purchase_price, new_quantity, asset_id))
                print(f"Updated position for {ticker}: {new_quantity} shares at ${purchase_price:.2f} per share.")

            self.conn.commit()
        else:
            print(f"No existing asset found for {ticker} in this portfolio.")

    def remove_asset(self, asset_id):
        """Removes an asset from the portfolio when it is sold."""
        self.cursor.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
        self.conn.commit()

    def load_valid_tickers(self, filename="SnP_tickers_sector.csv"):
        """
        Loads valid stock tickers and their corresponding asset names and sectors from a CSV file.
        Expected CSV headers: Symbol, Security, GICS Sector, GICS Sub-Industry, Headquarters Location, Date added, CIK, Founded.
        """
        tickers = {}
        try:
            with open(filename, 'r') as file:
                reader = csv.reader(file)
                headers = next(reader, None)  # Skip header row if present
                for row in reader:
                    # Use the first three columns: Symbol, Security, and GICS Sector.
                    ticker = row[0].strip().upper()
                    name = row[1].strip()
                    sector = row[2].strip() if len(row) > 2 else "Unknown"
                    tickers[ticker] = {"name": name, "sector": sector}
        except FileNotFoundError:
            print(f"File {filename} not found.")
        return tickers


class PortfolioManager:
    def __init__(self):
        self.db = DatabaseManager()
        self.valid_tickers = self.db.load_valid_tickers()

    def register(self, name):
        return self.db.register_user(name)

    def login(self, name):
        return self.db.login_user(name)

    def get_market_price(self, ticker):
        """Fetch the latest market price from Yahoo Finance."""
        try:
            stock = yf.Ticker(ticker)
            stock_data = stock.history(period="1d")
            if not stock_data.empty:
                return stock_data["Close"].iloc[-1]
            else:
                return None
        except Exception as e:
            print(f"Error fetching market data for {ticker}: {e}")
            return None

    def create_portfolio(self, owner_id, name):
        self.db.cursor.execute("SELECT id FROM portfolios WHERE owner_id = ?", (owner_id,))
        existing_portfolio = self.db.cursor.fetchone()

        if existing_portfolio:
            print(f"User already has a portfolio with ID {existing_portfolio[0]}.")
            return existing_portfolio[0]
        else:
            return self.db.insert_portfolio(owner_id, name)

    def update_stock_in_portfolio(self, portfolio_id, ticker, purchase_price, quantity, order_type, limit_price=None):
        """Update the stock's record in the portfolio, either buying more or shorting more."""
        self.db.cursor.execute("SELECT quantity, purchase_price FROM assets WHERE portfolio_id = ? AND ticker = ?", (portfolio_id, ticker))
        existing_asset = self.db.cursor.fetchone()

        if existing_asset:
            self.db.update_asset(portfolio_id, ticker, purchase_price, quantity, order_type)
        else:
            # Look up the asset name from our valid tickers; default to 'Unknown' if not found.
            asset_info = self.valid_tickers.get(ticker, {"name": "Unknown"})
            self.db.insert_asset(portfolio_id, ticker, asset_info.get("name", "Unknown"), purchase_price, quantity, order_type, limit_price)
            print(f"New position added for {ticker}: {quantity} shares.")

    def buy_stock(self, portfolio_id, ticker, name, purchase_price, quantity, order_type, limit_price=None):
        """Insert the new stock into the portfolio after buying."""
        self.db.insert_asset(portfolio_id, ticker, name, purchase_price, quantity, order_type, limit_price)
        print(f"Successfully bought {quantity} of {name} ({ticker}) at ${purchase_price:.2f} per share.")

    def buy_loop(self, portfolio_id):
        while True:
            ticker = input("Enter stock ticker (or type 'exit' to quit): ").upper()
            if ticker == "EXIT":
                break
            if ticker in self.valid_tickers:
                asset_name = self.valid_tickers[ticker]["name"]
                market_price = self.get_market_price(ticker)
                if market_price is None:
                    print(f"Could not retrieve market price for {ticker}. Please try again.")
                    continue

                print(f"\nStock found: {ticker} - {asset_name}")
                print(f"Current market price: ${market_price:.2f}")
                confirm = input(f"Do you want to buy {asset_name} ({ticker})? (y/n): ").lower()

                if confirm == 'y':
                    order_type = input("Enter order type (market/limit): ").lower()
                    if order_type == 'limit':
                        limit_price = float(input("Enter limit price: "))
                        self.update_stock_in_portfolio(portfolio_id, ticker, None, 0, order_type, limit_price)
                    elif order_type == 'market':
                        purchase_price = market_price
                        quantity = int(input("Enter quantity: "))
                        self.update_stock_in_portfolio(portfolio_id, ticker, purchase_price, quantity, order_type)
                    break
                else:
                    print("\nYou chose not to buy. Here are some suggested tickers based on your input:")
                    self.validate_ticker(ticker)
            else:
                print("\nNo matching ticker found. Here are some suggested tickers:")
                self.validate_ticker(ticker)

    def check_portfolio(self, portfolio_id):
        assets = self.db.check_portfolio(portfolio_id)
        if assets:
            print("\nCurrent Portfolio Holdings:")
            for asset in assets:
                asset_id, ticker, name, purchase_price, market_price, quantity, pnl = asset
                if quantity > 0:
                    print(f"Owned: {name} ({ticker}) - Purchase: ${purchase_price:.2f}, Market: ${market_price:.2f}, Quantity: {quantity}, P&L: ${pnl:.2f}")
                else:
                    short_pnl = (purchase_price - market_price) * abs(quantity)
                    print(f"Short: {name} ({ticker}) - Sale: ${purchase_price:.2f}, Market: ${market_price:.2f}, Quantity: {quantity}, P&L: ${short_pnl:.2f}")
        return assets

    def sell_asset_loop(self, portfolio_id):
        while True:
            ticker = input("Enter stock ticker to short (or type 'exit' to quit): ").upper()
            if ticker == "EXIT":
                break
            if ticker in self.valid_tickers:
                asset_name = self.valid_tickers[ticker]["name"]
                market_price = self.get_market_price(ticker)
                if market_price is None:
                    print(f"Could not retrieve market price for {ticker}. Please try again.")
                    continue

                print(f"\nAsset found: {asset_name} ({ticker})")
                print(f"Current market price: ${market_price:.2f}")
                confirm = input(f"Do you want to short sell {asset_name} ({ticker})? (y/n): ").lower()
                if confirm == 'y':
                    order_type = input("Enter order type (market/limit): ").lower()
                    if order_type == 'limit':
                        limit_price = float(input("Enter limit price: "))
                        self.update_stock_in_portfolio(portfolio_id, ticker, None, -1, order_type, limit_price)
                    elif order_type == 'market':
                        quantity = int(input("Enter quantity to short: "))
                        self.update_stock_in_portfolio(portfolio_id, ticker, market_price, -quantity, order_type)
                    print(f"Successfully shorted {quantity} of {asset_name} ({ticker}) at ${market_price:.2f} per share.")
                    break
                else:
                    print("Short sale canceled.")
            else:
                print("\nNo matching ticker found. Here are some suggested tickers:")
                self.validate_ticker(ticker)

    def validate_ticker(self, ticker):
        """Suggests matching tickers for a given partial input."""
        matches = [valid_ticker for valid_ticker in self.valid_tickers if valid_ticker.startswith(ticker.upper())]
        if matches:
            print("Matching tickers:")
            for match in matches:
                print(f"{match} - {self.valid_tickers[match]['name']}")
        else:
            print("No matching tickers found.")
        return matches

    def export_portfolio(self, portfolio_id, filename="portfolio_export.csv"):
        """Exports the portfolio details to a CSV file."""
        assets = self.db.check_portfolio(portfolio_id)
        if assets:
            try:
                with open(filename, "w", newline="") as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(["Asset ID", "Ticker", "Name", "Purchase Price", "Market Price", "Quantity", "PnL"])
                    for asset in assets:
                        writer.writerow(asset)
                print(f"Portfolio exported to {filename}")
            except Exception as e:
                print(f"Error exporting portfolio: {e}")
        else:
            print("No assets to export.")

    def visualize_portfolio(self, portfolio_id):
        """Visualizes the portfolio performance with a bar chart showing current values."""
        assets = self.db.check_portfolio(portfolio_id)
        if not assets:
            print("No assets to visualize.")
            return

        tickers = []
        values = []
        for asset in assets:
            asset_id, ticker, name, purchase_price, market_price, quantity, pnl = asset
            tickers.append(ticker)
            values.append(market_price * quantity)

        plt.figure(figsize=(10, 6))
        plt.bar(tickers, values, color='skyblue')
        plt.xlabel('Ticker')
        plt.ylabel('Current Value ($)')
        plt.title('Portfolio Performance')
        plt.tight_layout()
        plt.show()

    def diversification_analysis(self, portfolio_id):
        """
        Analyzes diversification by computing the current value per sector.
        Uses the 'GICS Sector' from the CSV file and displays a breakdown and pie chart.
        """
        assets = self.db.check_portfolio(portfolio_id)
        if not assets:
            print("No assets to analyze for diversification.")
            return

        sector_values = {}
        total_value = 0
        for asset in assets:
            asset_id, ticker, name, purchase_price, market_price, quantity, pnl = asset
            value = market_price * quantity
            total_value += value

            # Lookup the sector from valid tickers; default to "Unknown" if missing.
            if ticker in self.valid_tickers:
                sector = self.valid_tickers[ticker].get("sector", "Unknown")
            else:
                sector = "Unknown"
            sector_values[sector] = sector_values.get(sector, 0) + value

        print("\nDiversification Analysis:")
        for sector, value in sector_values.items():
            percentage = (value / total_value * 100) if total_value != 0 else 0
            print(f"{sector}: ${value:.2f} ({percentage:.2f}%)")

        # Pie chart visualization for diversification.
        labels = list(sector_values.keys())
        sizes = [value for value in sector_values.values()]
        plt.figure(figsize=(8, 8))
        plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140)
        plt.title("Portfolio Diversification by Sector")
        plt.axis('equal')
        plt.show()


if __name__ == "__main__":
    manager = PortfolioManager()

    name = input("Enter your name: ")
    user_id = manager.login(name) or manager.register(name)

    portfolio_name = f"{name}'s Portfolio"
    portfolio_id = manager.create_portfolio(user_id, portfolio_name)

    while True:
        print("\nOptions: 1) Buy Stock  2) Check Portfolio  3) Short Sell Stock  4) Export Portfolio  5) Visualize Portfolio  6) Diversification Analysis  7) Exit")
        choice = input("Enter choice: ")

        if choice == "1":
            manager.buy_loop(portfolio_id)
        elif choice == "2":
            manager.check_portfolio(portfolio_id)
        elif choice == "3":
            manager.sell_asset_loop(portfolio_id)
        elif choice == "4":
            manager.export_portfolio(portfolio_id)
        elif choice == "5":
            manager.visualize_portfolio(portfolio_id)
        elif choice == "6":
            manager.diversification_analysis(portfolio_id)
        elif choice == "7":
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please enter a valid option.")
