/**
 * Phillies Cards Manager - Frontend Application
 */

class PhilliesCardsApp {
    constructor() {
        this.currentView = 'years';
        this.currentYear = null;
        this.currentSet = null;
        this.searchResults = [];
        
        this.init();
    }
    
    init() {
        this.bindEvents();
        this.loadYears();
        this.loadStats();
    }
    
    bindEvents() {
        // Navigation tabs
        document.querySelectorAll('.nav-tab').forEach(tab => {
            tab.addEventListener('click', (e) => {
                this.switchView(e.target.dataset.view);
            });
        });
        
        // Search functionality
        document.getElementById('searchBtn').addEventListener('click', () => {
            this.performSearch();
        });
        
        document.getElementById('searchInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.performSearch();
            }
        });
        
        // Settings modal
        document.getElementById('settingsBtn').addEventListener('click', () => {
            this.showSettings();
        });
        
        document.getElementById('closeSettings').addEventListener('click', () => {
            this.hideSettings();
        });
        
        // Scrape latest year
        document.getElementById('scrapeLatestBtn').addEventListener('click', () => {
            this.scrapeLatestYear();
        });
        
        // Download images
        document.getElementById('downloadImagesBtn').addEventListener('click', () => {
            this.downloadImagesForYear(1992);
        });
        
        // Navigation back buttons
        document.getElementById('backToYears').addEventListener('click', () => {
            this.showYearsView();
        });
        
        document.getElementById('backToSets').addEventListener('click', () => {
            this.showSetsView();
        });
        
        document.getElementById('backToYearsFromSearch').addEventListener('click', () => {
            this.showYearsView();
        });
        
        // Close card modal
        document.getElementById('closeCardModal').addEventListener('click', () => {
            this.hideCardModal();
        });
        
        // Close modals when clicking outside
        window.addEventListener('click', (e) => {
            if (e.target.classList.contains('modal')) {
                this.hideSettings();
                this.hideCardModal();
            }
        });
    }
    
    async loadYears() {
        try {
            this.showLoading(true);
            const response = await fetch('/api/years');
            const data = await response.json();
            
            if (data.success) {
                this.renderYears(data.data);
            } else {
                this.showError('Failed to load years');
            }
        } catch (error) {
            console.error('Error loading years:', error);
            this.showError('Failed to load years');
        } finally {
            this.showLoading(false);
        }
    }
    
    renderYears(years) {
        const yearsGrid = document.getElementById('yearsGrid');
        yearsGrid.innerHTML = '';
        
        years.forEach(year => {
            const yearCard = document.createElement('div');
            yearCard.className = 'year-card';
            yearCard.innerHTML = `
                <h3>${year}</h3>
                <p>Click to view sets</p>
            `;
            
            yearCard.addEventListener('click', () => {
                this.loadSetsForYear(year);
            });
            
            yearsGrid.appendChild(yearCard);
        });
    }
    
    async loadSetsForYear(year) {
        try {
            this.currentYear = year;
            this.showLoading(true);
            
            const response = await fetch(`/api/sets/year/${year}`);
            const data = await response.json();
            
            if (data.success) {
                this.renderSets(data.data, year);
                this.showSetsView();
            } else {
                this.showError('Failed to load sets');
            }
        } catch (error) {
            console.error('Error loading sets:', error);
            this.showError('Failed to load sets');
        } finally {
            this.showLoading(false);
        }
    }
    
    renderSets(sets, year) {
        const setsGrid = document.getElementById('setsGrid');
        const yearTitle = document.getElementById('setsYearTitle');
        
        yearTitle.textContent = `${year} Sets`;
        setsGrid.innerHTML = '';
        
        sets.forEach(set => {
            const setCard = document.createElement('div');
            setCard.className = 'set-card';
            
            let subsetsHtml = '';
            if (set.subsets && set.subsets.length > 0) {
                subsetsHtml = `
                    <div class="set-subsets">
                        ${set.subsets.map(subset => `<span class="set-subset">${subset}</span>`).join('')}
                    </div>
                `;
            }
            
            setCard.innerHTML = `
                <h3>${set.name}</h3>
                <div class="set-count">${set.count} cards</div>
                ${subsetsHtml}
            `;
            
            setCard.addEventListener('click', () => {
                this.loadCardsForSet(set.name, year);
            });
            
            setsGrid.appendChild(setCard);
        });
    }
    
    async loadCardsForSet(setName, year) {
        try {
            this.currentSet = setName;
            this.showLoading(true);
            
            const response = await fetch(`/api/cards/year/${year}?limit=1000`);
            const data = await response.json();
            
            if (data.success) {
                // Filter cards for this specific set
                const setCards = data.data.filter(card => 
                    card.main_set_name === setName || 
                    (card.subset_name && card.subset_name.includes(setName))
                );
                
                this.renderCards(setCards, setName, year);
                this.showCardsView();
            } else {
                this.showError('Failed to load cards');
            }
        } catch (error) {
            console.error('Error loading cards:', error);
            this.showError('Failed to load cards');
        } finally {
            this.showLoading(false);
        }
    }
    
    renderCards(cards, setName, year) {
        const cardsGrid = document.getElementById('cardsGrid');
        const setTitle = document.getElementById('cardsSetTitle');
        
        setTitle.textContent = `${year} ${setName}`;
        cardsGrid.innerHTML = '';
        
        cards.forEach(card => {
            const cardItem = document.createElement('div');
            cardItem.className = 'card-item';
            
            // Parse metadata tags
            const metadataTags = this.parseMetadataTags(card.card_type);
            
            // Check if we have local images
            const hasFrontImage = card.local_front_image;
            const hasBackImage = card.local_back_image;
            
            cardItem.innerHTML = `
                <div class="card-header">
                    <span class="card-number">${card.card_number || 'NNO'}</span>
                    <input type="checkbox" class="card-checkbox" data-card-id="${card.id}">
                </div>
                <div class="card-image-container">
                    ${hasFrontImage ? 
                        `<img src="/static/images/front/${card.local_front_image.split('/').pop()}" alt="${card.player_name}" class="card-image" onerror="this.style.display='none'">` :
                        `<div class="card-image-placeholder">
                            <i class="fas fa-image"></i>
                            <span>No Image</span>
                        </div>`
                    }
                </div>
                <div class="card-player">${card.player_name}</div>
                <div class="card-set">${card.main_set_name}${card.subset_name ? ` - ${card.subset_name}` : ''}</div>
                <div class="card-metadata">
                    ${metadataTags.map(tag => `<span class="card-tag ${tag.class}">${tag.text}</span>`).join('')}
                </div>
                ${hasBackImage ? `<div class="card-back-indicator"><i class="fas fa-images"></i> Back Available</div>` : ''}
            `;
            
            // Add click handler for card details
            cardItem.addEventListener('click', (e) => {
                if (!e.target.classList.contains('card-checkbox')) {
                    this.showCardDetails(card);
                }
            });
            
            // Add checkbox change handler
            const checkbox = cardItem.querySelector('.card-checkbox');
            checkbox.addEventListener('change', (e) => {
                this.toggleCardOwned(card.id, e.target.checked);
            });
            
            cardsGrid.appendChild(cardItem);
        });
    }
    
    parseMetadataTags(metadataString) {
        if (!metadataString) return [];
        
        const tags = [];
        const parts = metadataString.split('|').map(part => part.trim());
        
        parts.forEach(part => {
            if (part) {
                let className = '';
                if (part.includes('RC')) className = 'rc';
                else if (part.includes('AU')) className = 'au';
                else if (part.includes('RELIC')) className = 'relic';
                else if (part.includes('SN')) className = 'sn';
                
                tags.push({
                    text: part,
                    class: className
                });
            }
        });
        
        return tags;
    }
    
    async performSearch() {
        const query = document.getElementById('searchInput').value.trim();
        if (!query) return;
        
        try {
            this.showLoading(true);
            const response = await fetch(`/api/cards/search?query=${encodeURIComponent(query)}`);
            const data = await response.json();
            
            if (data.success) {
                this.searchResults = data.data;
                this.renderSearchResults(data.data, query);
                this.switchView('search');
            } else {
                this.showError('Search failed');
            }
        } catch (error) {
            console.error('Error performing search:', error);
            this.showError('Search failed');
        } finally {
            this.showLoading(false);
        }
    }
    
    renderSearchResults(cards, query) {
        const searchGrid = document.getElementById('searchResultsGrid');
        const searchTitle = document.getElementById('searchResultsTitle');
        
        searchTitle.textContent = `Search Results for "${query}" (${cards.length} cards)`;
        searchGrid.innerHTML = '';
        
        cards.forEach(card => {
            const cardItem = document.createElement('div');
            cardItem.className = 'card-item';
            
            const metadataTags = this.parseMetadataTags(card.card_type);
            
            // Check if we have local images
            const hasFrontImage = card.local_front_image;
            const hasBackImage = card.local_back_image;
            
            cardItem.innerHTML = `
                <div class="card-header">
                    <span class="card-number">${card.card_number || 'NNO'}</span>
                    <input type="checkbox" class="card-checkbox" data-card-id="${card.id}">
                </div>
                <div class="card-image-container">
                    ${hasFrontImage ? 
                        `<img src="/static/images/front/${card.local_front_image.split('/').pop()}" alt="${card.player_name}" class="card-image" onerror="this.style.display='none'">` :
                        `<div class="card-image-placeholder">
                            <i class="fas fa-image"></i>
                            <span>No Image</span>
                        </div>`
                    }
                </div>
                <div class="card-player">${card.player_name}</div>
                <div class="card-set">${card.year} ${card.main_set_name}${card.subset_name ? ` - ${card.subset_name}` : ''}</div>
                <div class="card-metadata">
                    ${metadataTags.map(tag => `<span class="card-tag ${tag.class}">${tag.text}</span>`).join('')}
                </div>
                ${hasBackImage ? `<div class="card-back-indicator"><i class="fas fa-images"></i> Back Available</div>` : ''}
            `;
            
            cardItem.addEventListener('click', (e) => {
                if (!e.target.classList.contains('card-checkbox')) {
                    this.showCardDetails(card);
                }
            });
            
            const checkbox = cardItem.querySelector('.card-checkbox');
            checkbox.addEventListener('change', (e) => {
                this.toggleCardOwned(card.id, e.target.checked);
            });
            
            searchGrid.appendChild(cardItem);
        });
    }
    
    showCardDetails(card) {
        const modal = document.getElementById('cardModal');
        const title = document.getElementById('cardModalTitle');
        const content = document.getElementById('cardModalContent');
        
        title.textContent = `${card.player_name} - ${card.main_set_name}`;
        
        const metadataTags = this.parseMetadataTags(card.card_type);
        
        content.innerHTML = `
            <div class="card-details">
                <div class="detail-row">
                    <strong>Player:</strong> ${card.player_name}
                </div>
                <div class="detail-row">
                    <strong>Year:</strong> ${card.year}
                </div>
                <div class="detail-row">
                    <strong>Set:</strong> ${card.main_set_name}
                </div>
                ${card.subset_name ? `<div class="detail-row"><strong>Subset:</strong> ${card.subset_name}</div>` : ''}
                <div class="detail-row">
                    <strong>Card Number:</strong> ${card.card_number || 'NNO'}
                </div>
                ${card.card_type ? `<div class="detail-row"><strong>Type:</strong> ${card.card_type}</div>` : ''}
                <div class="detail-row">
                    <strong>TCDB URL:</strong> <a href="${card.tcdb_url}" target="_blank">View on TCDB</a>
                </div>
                ${card.front_photo_url ? `<div class="detail-row"><strong>Front Image:</strong> <a href="${card.front_photo_url}" target="_blank">View</a></div>` : ''}
                ${card.back_photo_url ? `<div class="detail-row"><strong>Back Image:</strong> <a href="${card.back_photo_url}" target="_blank">View</a></div>` : ''}
            </div>
        `;
        
        modal.classList.remove('hidden');
    }
    
    hideCardModal() {
        document.getElementById('cardModal').classList.add('hidden');
    }
    
    async loadStats() {
        try {
            const response = await fetch('/api/stats');
            const data = await response.json();
            
            if (data.success) {
                this.renderStats(data.data);
            }
        } catch (error) {
            console.error('Error loading stats:', error);
        }
    }
    
    renderStats(stats) {
        const statsDiv = document.getElementById('dbStats');
        
        statsDiv.innerHTML = `
            <div class="stat-item">
                <span class="stat-label">Total Cards:</span>
                <span class="stat-value">${stats.summary.total_cards}</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">Total Images:</span>
                <span class="stat-value">${stats.summary.total_images}</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">Database Size:</span>
                <span class="stat-value">${stats.summary.total_size_mb} MB</span>
            </div>
        `;
    }
    
    async scrapeLatestYear() {
        const button = document.getElementById('scrapeLatestBtn');
        const originalText = button.innerHTML;
        
        try {
            button.disabled = true;
            button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Scraping...';
            
            const response = await fetch('/api/scrape/latest', { method: 'POST' });
            const data = await response.json();
            
            if (data.success) {
                this.showSuccess(`Successfully scraped latest year: ${data.message}`);
                // Reload stats and years
                this.loadStats();
                this.loadYears();
            } else {
                this.showError(`Scraping failed: ${data.detail}`);
            }
        } catch (error) {
            console.error('Error scraping latest year:', error);
            this.showError('Scraping failed');
        } finally {
            button.disabled = false;
            button.innerHTML = originalText;
        }
    }
    
    async downloadImagesForYear(year) {
        const button = document.getElementById('downloadImagesBtn');
        const originalText = button.innerHTML;
        
        try {
            button.disabled = true;
            button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Triggering Download...';
            
            const response = await fetch(`/api/trigger/image-download/${year}`, { method: 'POST' });
            const data = await response.json();
            
            if (data.success) {
                this.showSuccess(`Image download triggered for ${year}. Run the download script to execute.`);
                // Reload stats to show current image count
                this.loadStats();
            } else {
                this.showError(`Image download trigger failed: ${data.detail}`);
            }
        } catch (error) {
            console.error('Error triggering image download:', error);
            this.showError('Image download trigger failed');
        } finally {
            button.disabled = false;
            button.innerHTML = originalText;
        }
    }
    
    toggleCardOwned(cardId, owned) {
        // TODO: Implement card ownership tracking
        console.log(`Card ${cardId} owned: ${owned}`);
    }
    
    switchView(viewName) {
        // Hide all views
        document.querySelectorAll('.view').forEach(view => {
            view.classList.remove('active');
        });
        
        // Show selected view
        const targetView = document.getElementById(`${viewName}View`);
        if (targetView) {
            targetView.classList.add('active');
        }
        
        // Update navigation tabs
        document.querySelectorAll('.nav-tab').forEach(tab => {
            tab.classList.remove('active');
        });
        
        const targetTab = document.querySelector(`[data-view="${viewName}"]`);
        if (targetTab) {
            targetTab.classList.add('active');
        }
        
        this.currentView = viewName;
        
        // Scroll to top when switching views
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
    
    showYearsView() {
        this.switchView('years');
    }
    
    showSetsView() {
        this.switchView('sets');
    }
    
    showCardsView() {
        this.switchView('cards');
    }
    
    showSettings() {
        document.getElementById('settingsModal').classList.remove('hidden');
    }
    
    hideSettings() {
        document.getElementById('settingsModal').classList.add('hidden');
    }
    
    showLoading(show) {
        const spinner = document.getElementById('loadingSpinner');
        if (show) {
            spinner.classList.remove('hidden');
        } else {
            spinner.classList.add('hidden');
        }
    }
    
    showError(message) {
        // Simple error display - could be enhanced with a toast notification system
        alert(`Error: ${message}`);
    }
    
    showSuccess(message) {
        // Simple success display - could be enhanced with a toast notification system
        alert(`Success: ${message}`);
    }
}

// Initialize the application when the DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new PhilliesCardsApp();
});
